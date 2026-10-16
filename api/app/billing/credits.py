"""Agent credits: the money agents spend on paid provider calls.

Money model: 1 credit = 1000 micro-USD ($0.001). AIsa reports real cost in
the ``x-aisa-customer-cost-micros-usd`` response header, which maps onto
credits 1:1 (rounded half-up).

The ``CreditsLedger`` is append-only: purchases and debits are entries,
balance is always derived — never stored. Webhook fulfillment is idempotent
per Stripe session id so event replays never double-credit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

MICROS_PER_CREDIT = 1000


def micros_to_credits(micros: int) -> int:
    """Round half-up: 20000 micros -> 20 credits, 5000 -> 5."""
    if micros <= 0:
        return 0
    return (micros + MICROS_PER_CREDIT // 2) // MICROS_PER_CREDIT


def credits_to_usd(credits: int) -> Decimal:
    """Credits as a 2-decimal USD amount (5000 credits -> $5.00)."""
    return (Decimal(credits) / MICROS_PER_CREDIT).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class CreditPack:
    pack_id: str
    usd_cents: int
    credits: int


CREDIT_PACKS: dict[str, CreditPack] = {
    "credits_5": CreditPack("credits_5", 500, 5000),
    "credits_20": CreditPack("credits_20", 2000, 20000),
    "credits_50": CreditPack("credits_50", 5000, 50000),
}


class InsufficientCredits(Exception):
    """A debit was attempted beyond the account's balance."""


@dataclass(frozen=True)
class CreditEntry:
    id: str
    created_at: datetime
    account_id: str
    kind: str  # "purchase" | "debit" | "refund" | "adjustment"
    credits: int  # signed: purchases positive, debits negative
    tool: str  # e.g. "stripe", "aisa.market.get_quote"
    meta: dict = field(default_factory=dict)


class CreditsLedger:
    """In-memory append-only credits ledger. ``balance()`` is derived."""

    def __init__(self) -> None:
        self._entries: list[CreditEntry] = []
        self._processed_sessions: set[str] = set()

    def _append(
        self, *, account_id: str, kind: str, credits: int, tool: str, meta: dict | None
    ) -> CreditEntry:
        entry = CreditEntry(
            id=uuid4().hex[:12],
            created_at=datetime.now(UTC),
            account_id=account_id,
            kind=kind,
            credits=credits,
            tool=tool,
            meta=dict(meta or {}),
        )
        self._entries.append(entry)
        return entry

    def credit(
        self, account_id: str, credits: int, *, tool: str = "stripe",
        meta: dict | None = None,
    ) -> CreditEntry:
        if credits <= 0:
            raise ValueError("credit amount must be positive")
        return self._append(
            account_id=account_id, kind="purchase", credits=credits,
            tool=tool, meta=meta,
        )

    def credit_unique(
        self, session_id: str, account_id: str, credits: int, *,
        tool: str = "stripe", meta: dict | None = None,
    ) -> CreditEntry | None:
        """Idempotent purchase: the first call wins, replays return None."""
        if session_id in self._processed_sessions:
            return None
        self._processed_sessions.add(session_id)
        return self.credit(account_id, credits, tool=tool, meta=meta)

    def debit(
        self, account_id: str, credits: int, *, tool: str,
        meta: dict | None = None, allow_partial: bool = False,
    ) -> tuple[CreditEntry, int]:
        """Debit credits. Returns (entry, shortfall).

        With ``allow_partial=True`` (the metering path: the paid call already
        happened) the debit floors at a zero balance and reports the
        shortfall in the entry meta instead of raising.
        """
        if credits <= 0:
            raise ValueError("debit amount must be positive")
        balance = self.balance(account_id)
        if balance < credits and not allow_partial:
            raise InsufficientCredits(
                f"account {account_id} has {balance} credits, needs {credits}"
            )
        debited = min(balance, credits)
        shortfall = credits - debited
        entry = self._append(
            account_id=account_id, kind="debit", credits=-debited, tool=tool,
            meta={**(meta or {}), "requested_credits": credits,
                  "shortfall_credits": shortfall},
        )
        return entry, shortfall

    def balance(self, account_id: str) -> int:
        return sum(e.credits for e in self._entries if e.account_id == account_id)

    def spent_since(self, account_id: str, since: datetime) -> int:
        """Credits debited at or after ``since`` (for daily/monthly caps)."""
        return sum(
            -e.credits
            for e in self._entries
            if e.account_id == account_id
            and e.kind == "debit"
            and e.created_at >= since
        )

    def list(
        self, account_id: str, *, kind: str | None = None,
        limit: int | None = None,
    ) -> list[CreditEntry]:
        entries = [
            e for e in self._entries
            if e.account_id == account_id and (kind is None or e.kind == kind)
        ]
        if limit is not None:
            entries = entries[-limit:]
        return list(entries)

    def reset(self) -> None:
        self._entries.clear()
        self._processed_sessions.clear()


_ledger = CreditsLedger()


def get_ledger() -> CreditsLedger:
    """Process-wide ledger singleton (reset by ``reset_metering`` in tests)."""
    return _ledger
