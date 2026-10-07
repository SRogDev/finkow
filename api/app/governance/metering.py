"""Metering + spending governor: agents spend credits on paid provider calls.

- ``MeteredPort`` wraps a paid port (AIsa adapters). Before each call it
  checks the ``SpendingGovernor`` (balance + daily/monthly caps) against a
  cost estimate; after a successful call it debits the ACTUAL cost from the
  ``x-aisa-customer-cost-micros-usd`` header (``last_cost_micros_usd``),
  falling back to the estimate when the header is absent. Free calls
  (cost 0, e.g. mocks) are never debited.
- ``CreditsExhausted`` subclasses ``ProviderError`` so the market-data
  fallback chain treats an empty wallet like any other provider failure
  (free direct quotes keep flowing); LLM/search have no free fallback, so
  endpoints map it to HTTP 402 with a top-up link.
- The account being billed comes from the ``current_account_id`` context var,
  set per request by the FastAPI layer. No account -> pass-through.

Caps come from the environment (credits; 1 credit = $0.001):
- ``FINKOW_DAILY_CAP_CREDITS`` (default 1000 = $1/day)
- ``FINKOW_MONTHLY_CAP_CREDITS`` (default 10000 = $10/month)
0 disables a cap. Cost estimates:
- ``FINKOW_COST_ESTIMATE_{MARKET,LLM,SEARCH}_MICROS``
  (defaults 20000/10000/16000 — observed live values).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime

from app.billing.credits import (
    CreditsLedger,
    get_ledger,
    micros_to_credits,
)
from app.ports import ProviderError

_current_account: ContextVar[str | None] = ContextVar(
    "finkow_account_id", default=None
)


def set_account(account_id: str | None):
    """Set the billed account for this context. Returns the reset token."""
    return _current_account.set(account_id)


def reset_account(token) -> None:
    _current_account.reset(token)


def current_account() -> str | None:
    return _current_account.get()


@contextmanager
def account_context(account_id: str | None) -> Iterator[None]:
    token = set_account(account_id)
    try:
        yield
    finally:
        reset_account(token)


class CreditsExhausted(ProviderError):
    """A paid call would exceed the account's balance or spending caps.

    Raised BEFORE the provider is called, so the agent never silently
    overspends. Subclasses ``ProviderError`` so fallback chains keep working.
    """


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _start_of_today_utc() -> datetime:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _start_of_month_utc() -> datetime:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class SpendingGovernor:
    """Balance + daily/monthly spending caps. ``check`` raises before spend."""

    def __init__(
        self,
        ledger: CreditsLedger | None = None,
        *,
        daily_cap_credits: int | None = None,
        monthly_cap_credits: int | None = None,
    ) -> None:
        self._ledger = ledger or get_ledger()
        self.daily_cap_credits = (
            _env_int("FINKOW_DAILY_CAP_CREDITS", 1000)
            if daily_cap_credits is None
            else daily_cap_credits
        )
        self.monthly_cap_credits = (
            _env_int("FINKOW_MONTHLY_CAP_CREDITS", 10000)
            if monthly_cap_credits is None
            else monthly_cap_credits
        )

    def _cap(self, value: int | None) -> int | None:
        return None if value == 0 else value

    def check(self, account_id: str, estimate_micros: int) -> int:
        """Validate a planned paid call. Returns the estimate in credits.

        Raises ``CreditsExhausted`` when the balance or a cap would be
        exceeded — always BEFORE the provider call happens.
        """
        need = micros_to_credits(estimate_micros)
        if need <= 0:
            return 0
        balance = self._ledger.balance(account_id)
        if balance < need:
            raise CreditsExhausted(
                f"insufficient credits: need ~{need}, balance is {balance}. "
                "Top up to let agents keep working."
            )
        daily = self._cap(self.daily_cap_credits)
        if daily is not None:
            spent = self._ledger.spent_since(account_id, _start_of_today_utc())
            if spent + need > daily:
                raise CreditsExhausted(
                    f"daily spending cap reached ({daily} credits/day). "
                    "Top up or wait for the cap to reset."
                )
        monthly = self._cap(self.monthly_cap_credits)
        if monthly is not None:
            spent = self._ledger.spent_since(account_id, _start_of_month_utc())
            if spent + need > monthly:
                raise CreditsExhausted(
                    f"monthly spending cap reached ({monthly} credits/month). "
                    "Top up or wait for the cap to reset."
                )
        return need


class MeteredPort:
    """Wrap a paid provider port with cap-check-then-debit metering.

    Only async methods are metered; attributes pass through (mirrors the
    ``wrap_port`` rate-limiter pattern).
    """

    def __init__(
        self,
        port,
        *,
        ledger: CreditsLedger | None = None,
        governor: SpendingGovernor | None = None,
        tool: str = "aisa",
        estimate_micros: int = 20000,
        max_price_usd: float | None = None,
    ) -> None:
        self._port = port
        self._ledger = ledger or get_ledger()
        self._governor = governor or get_governor()
        self._tool = tool
        self._estimate_micros = estimate_micros
        self._max_price_usd = max_price_usd
        self.name = getattr(port, "name", "metered")

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        attr = getattr(self._port, name)
        if not callable(attr):
            return attr

        async def metered(*args, **kwargs):
            account_id = current_account()
            if account_id is None:
                return await attr(*args, **kwargs)
            if (
                self._max_price_usd is not None
                and self._estimate_micros > self._max_price_usd * 1_000_000
            ):
                raise CreditsExhausted(
                    f"estimated cost ${self._estimate_micros / 1_000_000:.4f} "
                    f"exceeds per-call limit ${self._max_price_usd:.4f}"
                )
            self._governor.check(account_id, self._estimate_micros)
            result = await attr(*args, **kwargs)
            micros = getattr(self._port, "last_cost_micros_usd", None)
            if micros is None:
                micros = self._estimate_micros
            credits = micros_to_credits(micros)
            if credits > 0:
                self._ledger.debit(
                    account_id,
                    credits,
                    tool=f"{self._tool}.{name}",
                    meta={"micros": micros},
                    allow_partial=True,
                )
            return result

        return metered


_governor: SpendingGovernor | None = None


def get_governor() -> SpendingGovernor:
    """Process-wide governor singleton (env-configured)."""
    global _governor
    if _governor is None:
        _governor = SpendingGovernor()
    return _governor


def reset_metering() -> None:
    """Test hook: fresh ledger, fresh governor, cleared account context."""
    global _governor
    get_ledger().reset()
    _governor = None
    set_account(None)
