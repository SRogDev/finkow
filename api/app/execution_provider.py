"""Execution-provider contract: what a REAL brokerage integration must
satisfy.

No provider is chosen (Roger's decision — stays OPEN). This module defines
the interface a real integration must implement, the exact data each method
needs, and the gates that keep mock output out of any real path.

Why the mock can never satisfy this interface:
- it produces no ``provider_order_id`` (the provider's own order id is
  REQUIRED on every real result — ``assert_real_execution_result``
  rejects anything without one);
- it has no partial fills, no real settlement, no market-hours
  enforcement, and fills instantly at mock prices;
- constructing it in real mode makes every submission raise
  ``LiveTradingDisabledError`` — it refuses to simulate real execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.brokerage import LiveTradingDisabledError, OrderSide
from app.modes import REAL_NOT_CONFIGURED, Mode
from app.money import to_cash, to_qty
from app.orders import OrderStatus
from app.store import utcnow  # re-exported from app.ids; kept for clarity


class RealExecutionContractError(Exception):
    """A result was presented as real execution without satisfying the
    real-execution contract (provider order id, non-simulated)."""


# ---------------------------------------------------------------- data


@dataclass(frozen=True)
class ProviderAccountRef:
    """Which brokerage account an operation targets.

    ``mode`` must be ``Mode.REAL``: providers never see experimental
    accounts — experimental money lives in the mock, never at a broker.
    """

    account_id: str  # Finkow account id
    owner_user_id: str
    mode: Mode
    provider_account_id: str | None = None  # the broker's account id


@dataclass(frozen=True)
class ProviderOrderRequest:
    """Everything a provider needs to route an order."""

    symbol: str
    side: OrderSide
    qty: Decimal
    order_type: str  # "market" | "limit" | "stop" | ...
    time_in_force: str  # "day" | "gtc" | "ioc" | ...
    idempotency_key: str  # REQUIRED: the provider dedupes on this
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.idempotency_key:
            raise ValueError("idempotency_key is required for real orders")


@dataclass(frozen=True)
class ProviderOrderResult:
    """What a provider must return for every order operation.

    ``provider_order_id`` is the broker's own order id and is REQUIRED
    (non-empty) for anything claimed as real execution. ``simulated`` is
    False for real results; the mock always returns True and
    ``provider_order_id=None``.
    """

    provider_order_id: str | None
    symbol: str
    side: OrderSide
    qty: Decimal
    status: OrderStatus
    simulated: bool = False
    filled_qty: Decimal = Decimal("0")
    avg_fill_price: Decimal | None = None
    submitted_at: datetime = field(default_factory=utcnow)
    raw: dict = field(default_factory=dict)  # provider-native payload, auditable


@dataclass(frozen=True)
class ProviderPosition:
    symbol: str
    qty: Decimal
    avg_cost: Decimal
    market_value: Decimal
    simulated: bool = False


@dataclass(frozen=True)
class ProviderAccountInfo:
    cash: Decimal
    buying_power: Decimal
    currency: str = "USD"
    live: bool = True  # False only for sandbox/paper provider accounts
    account_number: str | None = None


@dataclass(frozen=True)
class MarketHours:
    """When the provider accepts/routes orders."""

    timezone: str  # IANA, e.g. "America/New_York"
    regular_open: str  # "09:30" local
    regular_close: str  # "16:00" local
    extended_hours_supported: bool = False
    holidays_observed: tuple[str, ...] = ()  # ISO dates, e.g. "2026-11-26"


@dataclass(frozen=True)
class ProviderCapabilities:
    """What the integration can actually do. A real provider must report
    ``real_execution=True`` AND satisfy ``assert_real_execution_result`` on
    every result it returns."""

    real_execution: bool
    provides_provider_order_ids: bool
    partial_fills: bool
    real_settlement: bool
    supported_order_types: tuple[str, ...] = ("market",)
    supports_fractional: bool = False
    rate_limit_per_minute: int | None = None
    market_hours_timezone: str = "America/New_York"


def assert_real_execution_result(result: ProviderOrderResult) -> None:
    """Gate: reject anything that is not provably a real execution record.

    This is the check the (unwired) real path would run on every provider
    result. The mock can never pass it.
    """
    if result.simulated:
        raise RealExecutionContractError(
            "result is marked simulated: not a real execution record"
        )
    if not result.provider_order_id:
        raise RealExecutionContractError(
            "result has no provider_order_id: not a real execution record"
        )


# ---------------------------------------------------------------- protocol


@runtime_checkable
class ExecutionProvider(Protocol):
    """REQUIRED contract for a real execution integration.

    All methods are async. ``account`` is always a real-mode account;
    experimental accounts never reach a provider. Every mutating call is
    idempotent on the provider side via ``ProviderOrderRequest.idempotency_key``.
    """

    @property
    def name(self) -> str:
        """Human name of the integration, e.g. "alpaca"."""
        ...

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Honest capability advertisement; checked before any real call."""
        ...

    def market_hours(self) -> MarketHours:
        """Trading calendar the provider routes under."""
        ...

    async def submit(
        self, account: ProviderAccountRef, request: ProviderOrderRequest
    ) -> ProviderOrderResult:
        """Route an order. Needs: provider credentials, the provider's
        account id, symbol/side/qty, order type, time in force, and the
        idempotency key. Returns the provider's order id."""
        ...

    async def cancel(
        self, account: ProviderAccountRef, provider_order_id: str
    ) -> ProviderOrderResult:
        """Cancel an open order; returns its final provider-side status."""
        ...

    async def get_order(
        self, account: ProviderAccountRef, provider_order_id: str
    ) -> ProviderOrderResult | None:
        """Provider-side order status. Used by reconciliation: a timeout
        does NOT prove failure — this is queried BEFORE any retry."""
        ...

    async def list_open_orders(
        self, account: ProviderAccountRef
    ) -> list[ProviderOrderResult]:
        """All non-terminal provider-side orders for the account."""
        ...

    async def sync_positions(
        self, account: ProviderAccountRef
    ) -> list[ProviderPosition]:
        """Authoritative positions from the provider (settlement truth)."""
        ...

    async def get_account_info(
        self, account: ProviderAccountRef
    ) -> ProviderAccountInfo:
        """Authoritative cash/buying power from the provider."""
        ...


# ---------------------------------------------------------------- mock


class MockExecutionProvider:
    """Structural implementation of ``ExecutionProvider`` for the paper
    path. Satisfies the Protocol's shape but NEVER the real contract:
    every result is ``simulated=True`` with ``provider_order_id=None``, and
    real-mode submissions raise ``LiveTradingDisabledError``."""

    name = "mock"

    def __init__(self, price_fn=None) -> None:
        self._price_fn = price_fn
        self._fills: list[ProviderOrderResult] = []

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            real_execution=False,
            provides_provider_order_ids=False,
            partial_fills=False,
            real_settlement=False,
            supported_order_types=("market",),
            supports_fractional=True,
            rate_limit_per_minute=None,
        )

    def market_hours(self) -> MarketHours:
        # The mock has no market calendar: it fills instantly, always.
        # A real provider MUST supply real hours; the mock's instant fill
        # is one more reason it can never satisfy the interface.
        return MarketHours(
            timezone="UTC",
            regular_open="00:00",
            regular_close="23:59",
            extended_hours_supported=True,
        )

    def _price(self, symbol: str) -> Decimal:
        if self._price_fn is None:
            from app.providers.mock import _MOCK_UNIVERSE

            try:
                return Decimal(_MOCK_UNIVERSE[symbol.upper().strip()][0])
            except KeyError as exc:
                raise ValueError(f"unknown symbol: {symbol}") from exc
        return self._price_fn(symbol)

    async def submit(
        self, account: ProviderAccountRef, request: ProviderOrderRequest
    ) -> ProviderOrderResult:
        if account.mode is Mode.REAL:
            # Never simulate a real order: fail loudly instead.
            raise LiveTradingDisabledError(REAL_NOT_CONFIGURED)
        price = self._price(request.symbol)
        qty = to_qty(request.qty)
        result = ProviderOrderResult(
            provider_order_id=None,  # mock: no provider, no provider order id
            symbol=request.symbol.upper().strip(),
            side=request.side,
            qty=qty,
            status=OrderStatus.FILLED,
            simulated=True,
            filled_qty=qty,
            avg_fill_price=to_cash(price),
            raw={"mock": True, "idempotency_key": request.idempotency_key},
        )
        self._fills.append(result)
        return result

    async def cancel(
        self, account: ProviderAccountRef, provider_order_id: str
    ) -> ProviderOrderResult:
        raise RealExecutionContractError(
            "the mock has no provider-side orders to cancel: nothing real"
            " was ever submitted"
        )

    async def get_order(
        self, account: ProviderAccountRef, provider_order_id: str
    ) -> ProviderOrderResult | None:
        # No provider state exists; a real integration would query the
        # broker here during reconciliation.
        return None

    async def list_open_orders(
        self, account: ProviderAccountRef
    ) -> list[ProviderOrderResult]:
        return []

    async def sync_positions(
        self, account: ProviderAccountRef
    ) -> list[ProviderPosition]:
        return [
            ProviderPosition(
                symbol=f.symbol,
                qty=f.qty,
                avg_cost=f.avg_fill_price or Decimal("0"),
                market_value=to_cash(f.qty * (f.avg_fill_price or Decimal("0"))),
                simulated=True,
            )
            for f in self._fills
            if f.side is OrderSide.BUY
        ]

    async def get_account_info(
        self, account: ProviderAccountRef
    ) -> ProviderAccountInfo:
        return ProviderAccountInfo(
            cash=Decimal("0"),
            buying_power=Decimal("0"),
            currency="USD",
            live=False,  # the mock is never a live account
            account_number=None,
        )
