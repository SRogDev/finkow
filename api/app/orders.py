"""Order lifecycle: explicit states, validated transitions, idempotency,
risk checks, and reconciliation.

Paper-trade path (mock): propose -> draft, human confirm ->
awaiting_authorization -> submitted -> filled. The mock fills instantly, so a
mock fill is recorded as ``filled`` with ``simulated=True`` and
``provider_order_id=None`` — a mock fill can never be confused with a real
execution record.

Real providers will additionally produce ``partially_filled``; the states
exist in the enum so a future provider maps 1:1 instead of inventing new
ones.

Reconciliation rule (non-negotiable): a timeout does NOT prove failure. An
order stuck in a non-terminal state must be reconciled against the
provider's records before any retry. The mock has no provider, so a stuck
mock order is an internal inconsistency to investigate — never silently
retried, never assumed failed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from app.ids import new_id, utcnow
from app.modes import REAL_NOT_CONFIGURED, LiveTradingDisabledError, Mode, check_mode
from app.money import to_cash, to_qty

if TYPE_CHECKING:
    from app.store import Store


class OrderStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_AUTHORIZATION = "awaiting_authorization"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    FAILED = "failed"


_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    # propose: nothing has moved yet
    OrderStatus.DRAFT: frozenset(
        {
            # human/system authorized -> waiting on the (human) confirm step
            OrderStatus.AWAITING_AUTHORIZATION,
            # auto-authorized system paths (legacy direct execution) go
            # straight to submitted; recorded with actor="system"
            OrderStatus.SUBMITTED,
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
        }
    ),
    OrderStatus.AWAITING_AUTHORIZATION: frozenset(
        {
            OrderStatus.SUBMITTED,
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
        }
    ),
    OrderStatus.SUBMITTED: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
            OrderStatus.FAILED,
        }
    ),
    OrderStatus.PARTIALLY_FILLED: frozenset(
        {
            OrderStatus.FILLED,
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
            OrderStatus.FAILED,
        }
    ),
    # terminal: nothing leaves these states
    OrderStatus.FILLED: frozenset(),
    OrderStatus.REJECTED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.FAILED: frozenset(),
}

TERMINAL_STATUSES = frozenset(
    {
        OrderStatus.FILLED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
        OrderStatus.FAILED,
    }
)


class IllegalOrderTransitionError(Exception):
    """An order was asked to move between states the lifecycle forbids."""


class RiskLimitBreach(Exception):
    """A risk control blocked an order before submission."""

    def __init__(self, reason: str, limit: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.limit = limit


def transition(from_status: OrderStatus, to_status: OrderStatus) -> None:
    """Validate a single state transition; raises on illegal moves."""
    if to_status not in _TRANSITIONS[from_status]:
        raise IllegalOrderTransitionError(
            f"illegal order transition: {from_status.value} -> {to_status.value}"
        )


@dataclass(frozen=True)
class RiskLimits:
    """Risk/authorization controls enforced before any order is submitted."""

    max_trade_usd: Decimal = Decimal("25000")
    max_daily_trades_per_account: int = 20
    max_daily_trades_per_user: int = 50


@dataclass
class Order:
    """A single order and its lifecycle state.

    ``provider_order_id`` is the brokerage's own order id. It is ``None``
    for every mock/simulated order — by construction, no mock record can
    satisfy a real-execution check that requires it.
    """

    id: str
    account_id: str
    symbol: str
    side: str  # "buy" | "sell"
    qty: Decimal
    order_type: str = "market"
    time_in_force: str = "day"
    status: OrderStatus = OrderStatus.DRAFT
    filled_qty: Decimal = Decimal("0")
    avg_fill_price: Decimal | None = None
    provider_order_id: str | None = None
    simulated: bool = True
    idempotency_key: str | None = None
    approval_id: str | None = None
    reject_reason: str | None = None
    mode: Mode = Mode.EXPERIMENTAL
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


@dataclass(frozen=True)
class ReconciliationReport:
    """Result of reconciling an order against recorded state.

    For real providers this is where the provider-side status lands; the
    hook is :meth:`OrderLifecycle.reconcile` reading the provider through
    an ``ExecutionProvider``. A timeout never proves failure: a stuck order
    is reported inconsistent with an investigation action, never assumed.
    """

    order_id: str
    recorded_status: OrderStatus
    consistent: bool
    notes: list[str]
    action_required: str | None
    provider_order_id: str | None
    simulated: bool


class OrderLifecycle:
    """Drives orders through the lifecycle against any ``Store``.

    The store is duck-typed on the order methods (``save_order``,
    ``get_order``, ``get_order_by_idempotency_key``, ``list_orders``,
    ``list_accounts_by_owner``) so the lifecycle works on memory, SQLite,
    and future adapters without storage-specific code.
    """

    def __init__(self, store: Store, limits: RiskLimits | None = None) -> None:
        self._store = store
        self._limits = limits or RiskLimits()

    # ------------------------------------------------------------ creation

    def create(
        self,
        *,
        account_id: str,
        symbol: str,
        side: str,
        qty: Decimal,
        order_type: str = "market",
        time_in_force: str = "day",
        idempotency_key: str | None = None,
        approval_id: str | None = None,
        mode: Mode = Mode.EXPERIMENTAL,
        simulated: bool = True,
    ) -> tuple[Order, bool]:
        """Create a draft order. Idempotent: resubmitting the same key for
        the same account returns the original order with ``created=False``
        instead of duplicating it.

        Real mode never reaches a provider here: creating a real-mode order
        raises ``LiveTradingDisabledError`` — the mock must never simulate
        real execution.
        """
        if mode is Mode.REAL:
            raise LiveTradingDisabledError(REAL_NOT_CONFIGURED)
        account = self._store.get_account(account_id)
        if account is None:
            raise ValueError(f"account not found: {account_id}")
        check_mode(account.mode, mode, f"order on account {account_id}")
        if idempotency_key:
            existing = self._store.get_order_by_idempotency_key(
                account_id, idempotency_key
            )
            if existing is not None:
                return existing, False
        side = side.lower()
        if side not in ("buy", "sell"):
            raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
        qty = to_qty(qty)
        if qty <= 0:
            raise ValueError("quantity must be positive")
        order = Order(
            id=new_id(),
            account_id=account_id,
            symbol=symbol.upper().strip(),
            side=side,
            qty=qty,
            order_type=order_type,
            time_in_force=time_in_force,
            idempotency_key=idempotency_key,
            approval_id=approval_id,
            mode=mode,
            simulated=simulated,
        )
        self._store.save_order(order)
        return order, True

    # ------------------------------------------------------------ transitions

    def _move(self, order_id: str, to: OrderStatus) -> Order:
        order = self._store.get_order(order_id)
        if order is None:
            raise ValueError(f"order not found: {order_id}")
        transition(order.status, to)
        order.status = to
        order.updated_at = utcnow()
        self._store.save_order(order)
        return order

    def authorize(
        self,
        order_id: str,
        *,
        est_price: Decimal | None = None,
        limits: RiskLimits | None = None,
    ) -> Order:
        """Risk-gated authorization: draft -> awaiting_authorization.

        Runs the risk controls (per-trade USD cap, daily account/user
        limits) when an estimated price is supplied. A breach raises
        ``RiskLimitBreach`` WITHOUT transitioning — the caller records the
        order as rejected.
        """
        order = self._store.get_order(order_id)
        if order is None:
            raise ValueError(f"order not found: {order_id}")
        if est_price is not None:
            self._check_risk(order, to_cash(est_price), limits or self._limits)
        return self._move(order_id, OrderStatus.AWAITING_AUTHORIZATION)

    def authorize_direct(
        self,
        order_id: str,
        *,
        est_price: Decimal | None = None,
        limits: RiskLimits | None = None,
    ) -> Order:
        """Auto-authorized system path: same risk checks, then
        draft -> submitted in one step. Used by direct (non-human-gated)
        paper execution; the actor is recorded as "system" by callers."""
        order = self._store.get_order(order_id)
        if order is None:
            raise ValueError(f"order not found: {order_id}")
        if est_price is not None:
            self._check_risk(order, to_cash(est_price), limits or self._limits)
        return self._move(order_id, OrderStatus.SUBMITTED)

    def _check_risk(
        self, order: Order, est_price: Decimal, limits: RiskLimits
    ) -> None:
        est_value = to_cash(order.qty * est_price)
        if est_value > limits.max_trade_usd:
            raise RiskLimitBreach(
                f"order value ${est_value} exceeds max_trade_usd"
                f" ${limits.max_trade_usd}",
                limit="max_trade_usd",
            )
        if self._trades_today(order.account_id) >= limits.max_daily_trades_per_account:
            raise RiskLimitBreach(
                "daily trade limit reached for this account",
                limit="max_daily_trades_per_account",
            )
        account = self._store.get_account(order.account_id)
        owner = getattr(account, "owner_user_id", "") if account else ""
        if (
            owner
            and self._trades_today_by_user(owner) >= limits.max_daily_trades_per_user
        ):
            raise RiskLimitBreach(
                "daily trade limit reached for this user",
                limit="max_daily_trades_per_user",
            )

    def submit(self, order_id: str) -> Order:
        """awaiting_authorization (or auto-authorized draft) -> submitted."""
        return self._move(order_id, OrderStatus.SUBMITTED)

    def record_partial_fill(
        self,
        order_id: str,
        *,
        filled_qty: Decimal,
        avg_fill_price: Decimal,
        provider_order_id: str | None = None,
        simulated: bool = True,
    ) -> Order:
        """submitted -> partially_filled. The mock never produces these;
        real providers will."""
        order = self._store.get_order(order_id)
        if order is None:
            raise ValueError(f"order not found: {order_id}")
        filled_qty = to_qty(filled_qty)
        if filled_qty <= 0 or filled_qty >= order.qty:
            raise ValueError(
                f"partial fill qty must be within (0, {order.qty}), "
                f"got {filled_qty}"
            )
        self._move(order_id, OrderStatus.PARTIALLY_FILLED)
        order = self._store.get_order(order_id)
        assert order is not None
        order.filled_qty = filled_qty
        order.avg_fill_price = to_cash(avg_fill_price)
        order.provider_order_id = provider_order_id
        order.simulated = simulated
        order.updated_at = utcnow()
        self._store.save_order(order)
        return order

    def record_fill(
        self,
        order_id: str,
        *,
        filled_qty: Decimal,
        avg_fill_price: Decimal,
        provider_order_id: str | None = None,
        simulated: bool = True,
    ) -> Order:
        """submitted|partially_filled -> filled."""
        order = self._store.get_order(order_id)
        if order is None:
            raise ValueError(f"order not found: {order_id}")
        filled_qty = to_qty(filled_qty)
        if filled_qty != order.qty:
            raise ValueError(
                f"full fill qty must equal the order qty {order.qty}, "
                f"got {filled_qty}"
            )
        self._move(order_id, OrderStatus.FILLED)
        order = self._store.get_order(order_id)
        assert order is not None
        order.filled_qty = filled_qty
        order.avg_fill_price = to_cash(avg_fill_price)
        order.provider_order_id = provider_order_id
        order.simulated = simulated
        order.updated_at = utcnow()
        self._store.save_order(order)
        return order

    def reject(self, order_id: str, reason: str) -> Order:
        order = self._move(order_id, OrderStatus.REJECTED)
        order.reject_reason = reason
        order.updated_at = utcnow()
        self._store.save_order(order)
        return order

    def cancel(self, order_id: str, reason: str) -> Order:
        order = self._move(order_id, OrderStatus.CANCELLED)
        order.reject_reason = reason
        order.updated_at = utcnow()
        self._store.save_order(order)
        return order

    def fail(self, order_id: str, reason: str) -> Order:
        """Mark failed: submission errored with UNKNOWN outcome. Callers
        must reconcile against the provider before retrying."""
        order = self._move(order_id, OrderStatus.FAILED)
        order.reject_reason = reason
        order.updated_at = utcnow()
        self._store.save_order(order)
        return order

    # ------------------------------------------------------------ reconcile

    def reconcile(self, order_id: str) -> ReconciliationReport:
        """Re-read the order from the store and verify it is coherent.

        This is the mock's reconciliation: it re-reads recorded state
        rather than trusting the caller's copy. For a real provider, this
        is where ``ExecutionProvider.get_order(provider_order_id)`` is
        queried BEFORE any retry — a timeout does NOT prove failure.

        Real-provider hook: when ``order.provider_order_id`` is set and a
        provider is wired, query the provider here and compare
        provider-side status against the recorded one.
        """
        order = self._store.get_order(order_id)
        if order is None:
            raise ValueError(f"order not found: {order_id}")
        notes: list[str] = []
        simulated_note = (
            "simulated fill recorded locally; never a real execution"
            if order.simulated
            else "REAL execution record: provider_order_id must be set"
        )
        if order.status in TERMINAL_STATUSES:
            notes.append(f"order is terminal ({order.status.value})")
            notes.append(simulated_note)
            if order.status is OrderStatus.FILLED:
                notes.append(self._verify_fill(order))
            return ReconciliationReport(
                order_id=order.id,
                recorded_status=order.status,
                consistent=True,
                notes=notes,
                action_required=None,
                provider_order_id=order.provider_order_id,
                simulated=order.simulated,
            )
        # Non-terminal: the mock fills synchronously, so a stuck order is
        # unexpected. NEVER assume failed: investigate first.
        notes.append(
            f"order is in non-terminal state '{order.status.value}' with no"
            " recorded outcome"
        )
        notes.append(
            "a timeout does NOT prove failure: the provider must be queried"
            " before any retry"
        )
        notes.append(
            "no provider is wired for this order (mock path): treat as an"
            " internal inconsistency, do not retry blindly"
            if order.provider_order_id is None
            else f"query the provider for order {order.provider_order_id}"
            " before retrying"
        )
        return ReconciliationReport(
            order_id=order.id,
            recorded_status=order.status,
            consistent=False,
            notes=notes,
            action_required=(
                "investigate: reconcile the order against provider records"
                " before retrying or cancelling"
            ),
            provider_order_id=order.provider_order_id,
            simulated=order.simulated,
        )

    def _verify_fill(self, order: Order) -> str:
        txns = [
            t
            for t in self._store.list_transactions(order.account_id)
            if getattr(t, "order_id", None) == order.id
        ]
        if not txns:
            return (
                "WARNING: filled order has no linked transaction record —"
                " recorded fill is unverified"
            )
        linked_qty = sum((t.qty for t in txns), Decimal("0"))
        if linked_qty != order.qty:
            return (
                f"WARNING: linked transactions total {linked_qty} but the order"
                f" was for {order.qty}"
            )
        return (
            f"fill verified: {len(txns)} linked transaction(s) total"
            f" {linked_qty} {order.symbol}"
        )

    # ------------------------------------------------------------ helpers

    def list_for_approval(self, account_id: str, approval_id: str) -> list[Order]:
        return [
            o
            for o in self._store.list_orders(account_id)
            if o.approval_id == approval_id
        ]

    def _trades_today(self, account_id: str) -> int:
        """Trades executed today: filled orders plus legacy transactions
        that carry no order id (counted once, never twice)."""
        from datetime import UTC

        today = datetime.now(UTC).date()
        filled_orders = sum(
            1
            for o in self._store.list_orders(account_id)
            if o.status is OrderStatus.FILLED and o.created_at.date() == today
        )
        legacy_txns = sum(
            1
            for t in self._store.list_transactions(account_id)
            if getattr(t, "order_id", None) is None
            and t.created_at.date() == today
        )
        return filled_orders + legacy_txns

    def _trades_today_by_user(self, owner_user_id: str) -> int:
        total = 0
        for account in self._store.list_accounts_by_owner(owner_user_id):
            total += self._trades_today(account.id)
        return total
