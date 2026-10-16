"""InvestmentExecutor: paper-trade execution with limits, audit, and the human
confirmation gate.

Owns the v2 PortfolioPilot logic (moved here, not duplicated). Two ways to
move money:

- ``invest_paper`` — direct paper execution (the v2 behavior; used by the
  existing invest endpoint and tests).
- ``propose`` / ``confirm`` — the human confirmation gate, adapted from
  Polygrow's ``human_interrupt``: ``propose`` computes the trades WITHOUT
  moving money and stores a pending ``ApprovalRequest``; ``confirm`` executes
  only on explicit approval. Expired approvals never execute.

Limits (per executor): ``max_trade_usd`` per single trade and
``max_daily_trades`` per account/day. Breaches skip the trade and are
audit-logged.

Every money-affecting step is audit-logged. Paper money only: the live path
(``submit_live_order``) always raises ``LiveTradingDisabledError``.

``agent_name`` lets the legacy ``PortfolioPilot`` facade keep emitting the
exact v2 event stream ("pilot"/"pilot.invest_completed") while new callers
use "executor".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.agents.events import EventLog
from app.agents.planner import Allocation  # re-exported for callers
from app.brokerage import LiveTradingDisabledError
from app.governance.audit import AuditLog
from app.governance.metering import CreditsExhausted
from app.market import MarketDataError
from app.modes import REAL_NOT_CONFIGURED, Mode
from app.money import qty_str, to_cash, to_qty
from app.orders import (
    TERMINAL_STATUSES,
    Order,
    OrderLifecycle,
    RiskLimitBreach,
    RiskLimits,
)
from app.portfolio import value_portfolio
from app.ports import MarketDataPort, ProviderError
from app.store import ApprovalRequest, InMemoryStore, Snapshot, utcnow
from app.trading import (
    InsufficientFundsError,
    InsufficientPositionError,
    execute_paper_buy,
    execute_paper_sell,
)

# Below this dollar distance from target we call it "close enough".
_DUST = Decimal("1.00")

LIVE_TRADING_ENABLED = False


@dataclass(frozen=True)
class TradeRecord:
    side: str
    symbol: str
    quantity: str
    price: str


@dataclass(frozen=True)
class ProspectiveTrade:
    symbol: str
    side: str  # "buy" | "sell"
    qty: Decimal
    est_price: Decimal

    @property
    def est_value(self) -> Decimal:
        return to_cash(self.qty * self.est_price)


@dataclass(frozen=True)
class InvestResult:
    account_id: str
    trades: list[TradeRecord]
    total_invested: Decimal


class InvestmentExecutor:
    """Executes paper trades with limits, audit trail, and a confirmation gate."""

    def __init__(
        self,
        store: InMemoryStore,
        market: MarketDataPort,
        events: EventLog | None = None,
        audit: AuditLog | None = None,
        agent_name: str = "executor",
        max_trade_usd: Decimal = Decimal("25000"),
        max_daily_trades: int = 20,
        max_daily_trades_per_user: int = 50,
        approval_ttl: timedelta = timedelta(minutes=15),
    ) -> None:
        self._store = store
        self._market = market
        self._events = events or EventLog()
        self._audit = audit or AuditLog()
        self._agent_name = agent_name
        self._max_trade_usd = max_trade_usd
        self._max_daily_trades = max_daily_trades
        self._max_daily_trades_per_user = max_daily_trades_per_user
        self._approval_ttl = approval_ttl
        # Risk/authorization controls shared with the /api/orders path:
        # $25k/trade, daily per-account cap, and (now meaningful with
        # account ownership) a daily per-user cap across all their accounts.
        self._risk_limits = RiskLimits(
            max_trade_usd=max_trade_usd,
            max_daily_trades_per_account=max_daily_trades,
            max_daily_trades_per_user=max_daily_trades_per_user,
        )
        self._orders = OrderLifecycle(store)

    # ---------------------------------------------------------- live (disabled)

    def submit_live_order(self, symbol: str, qty: Decimal) -> None:
        """The live-trading path. Intentionally unwired — always raises."""
        raise LiveTradingDisabledError(REAL_NOT_CONFIGURED)

    # ---------------------------------------------------------- paper execution

    async def invest_paper(
        self, account_id: str, allocations: list[Allocation]
    ) -> InvestResult:
        """Direct paper execution toward target allocations (v2 behavior)."""
        account = self._store.get_account(account_id)
        if account is None:
            raise ValueError(f"account not found: {account_id}")
        targets = self._targets(allocations)
        self._events.append(
            self._agent_name,
            f"{self._agent_name}.invest_started",
            {"account_id": account_id, "targets": {s: str(w) for s, w in targets.items()}},
        )
        prospective = await self._plan_trades(account_id, targets)
        trades = self._execute_trades(account_id, prospective)
        self._events.append(
            self._agent_name,
            f"{self._agent_name}.invest_completed",
            {"account_id": account_id, "trades": len(trades)},
        )
        await self._snapshot(account_id)
        return InvestResult(
            account_id=account_id,
            trades=trades,
            total_invested=to_cash(sum(t.est_value for t in prospective if t.side == "buy")),
        )

    # ---------------------------------------------------------- confirmation gate

    async def propose(
        self, account_id: str, allocations: list[Allocation]
    ) -> ApprovalRequest:
        """Compute the trades WITHOUT moving money; store a pending approval."""
        account = self._store.get_account(account_id)
        if account is None:
            raise ValueError(f"account not found: {account_id}")
        if account.mode is Mode.REAL:
            # Refuse to plan real-money trades with the paper-trading engine:
            # planning with mock math and presenting it as a real proposal
            # would be simulated execution wearing a real label.
            raise LiveTradingDisabledError(REAL_NOT_CONFIGURED)
        targets = self._targets(allocations)
        prospective = await self._plan_trades(account_id, targets)
        trades = [
            {
                "symbol": t.symbol,
                "side": t.side,
                "qty": qty_str(t.qty),
                "est_price": qty_str(t.est_price),
                "est_value": str(t.est_value),
            }
            for t in prospective
        ]
        total = to_cash(sum(t.est_value for t in prospective))
        request = ApprovalRequest(
            account_id=account_id, trades=trades, total_usd=total,
            status="pending", mode=account.mode,
        )
        self._store.save_approval(request)
        # Every proposed trade becomes a draft order linked to the approval:
        # nothing is authorized or submitted until the human confirms.
        for t in prospective:
            self._orders.create(
                account_id=account_id,
                symbol=t.symbol,
                side=t.side,
                qty=t.qty,
                approval_id=request.id,
                mode=account.mode,
                simulated=True,
            )
        self._events.append(
            self._agent_name,
            f"{self._agent_name}.approval_requested",
            {"approval_id": request.id, "trades": len(trades)},
        )
        self._audit.append(
            actor=self._agent_name,
            action="approval.requested",
            account_id=account_id,
            details={"approval_id": request.id, "trades": len(trades), "total_usd": str(total)},
        )
        return request

    async def confirm(self, approval_id: str, approved: bool) -> dict:
        """Resolve a pending approval: execute on approval, cancel otherwise."""
        request = self._store.get_approval(approval_id)
        if request is None:
            raise ValueError(f"approval not found: {approval_id}")
        if request.status != "pending":
            raise ValueError(f"approval already {request.status}: {approval_id}")
        if datetime.now(UTC) - request.created_at > self._approval_ttl:
            request.status = "expired"
            request.decided_at = utcnow()
            self._store.save_approval(request)
            self._cancel_draft_orders(request.account_id, request.id,
                                      "approval expired")
            self._audit.append(
                actor=self._agent_name,
                action="approval.expired",
                account_id=request.account_id,
                outcome="rejected",
                details={"approval_id": approval_id},
            )
            return {"status": "expired", "trades": []}
        request.decided_at = utcnow()
        if not approved:
            request.status = "rejected"
            self._store.save_approval(request)
            self._cancel_draft_orders(request.account_id, request.id,
                                      "human rejected the approval")
            self._events.append(
                self._agent_name,
                f"{self._agent_name}.approval_rejected",
                {"approval_id": approval_id},
            )
            self._audit.append(
                actor="user",
                action="approval.rejected",
                account_id=request.account_id,
                outcome="rejected",
                details={"approval_id": approval_id},
            )
            return {"status": "rejected", "trades": []}
        request.status = "approved"
        self._store.save_approval(request)
        self._audit.append(
            actor="user",
            action="approval.granted",
            account_id=request.account_id,
            details={"approval_id": approval_id, "trades": len(request.trades)},
        )
        prospective = [
            ProspectiveTrade(
                symbol=t["symbol"],
                side=t["side"],
                qty=Decimal(t["qty"]),
                est_price=Decimal(t["est_price"]),
            )
            for t in request.trades
        ]
        # Draft orders were created by propose() in prospective order; the
        # human confirm drives them: draft -> awaiting_authorization ->
        # submitted -> filled (mock fills instantly, recorded simulated).
        orders = self._orders.list_for_approval(request.account_id, request.id)
        trades = self._execute_trades(request.account_id, prospective,
                                      orders=orders)
        await self._snapshot(request.account_id)
        self._events.append(
            self._agent_name,
            f"{self._agent_name}.invest_completed",
            {"account_id": request.account_id, "trades": len(trades)},
        )
        return {
            "status": "approved",
            "trades": [
                {
                    "side": t.side,
                    "symbol": t.symbol,
                    "quantity": t.quantity,
                    "price": t.price,
                }
                for t in trades
            ],
        }

    # ---------------------------------------------------------- internals

    def _targets(self, allocations: list[Allocation]) -> dict[str, Decimal]:
        targets = {a.symbol.upper().strip(): a.weight for a in allocations if a.weight > 0}
        if not targets:
            raise ValueError("no allocations to invest")
        return targets

    async def _plan_trades(
        self, account_id: str, targets: dict[str, Decimal]
    ) -> list[ProspectiveTrade]:
        """Dry-run: compute the trades that would move toward targets."""
        account = self._store.get_account(account_id)
        quotes = {}
        for symbol in targets:
            quotes[symbol] = await self._market.get_quote(symbol)
        pv = value_portfolio(account, self._store.get_positions(account_id), quotes)
        current_values = {p.symbol: p.market_value for p in pv.positions}
        out: list[ProspectiveTrade] = []
        for symbol, weight in targets.items():
            quote = quotes[symbol]
            if quote.price <= 0:
                continue
            target_value = to_cash(pv.total_value * weight)
            current = current_values.get(symbol, Decimal("0"))
            delta = target_value - current
            if abs(delta) < _DUST:
                continue
            if delta > 0:
                qty = to_qty(delta / quote.price)
                if qty <= 0:
                    continue
                out.append(ProspectiveTrade(symbol, "buy", qty, quote.price))
            else:
                position = self._store.get_position(account_id, symbol)
                if position is None:
                    continue
                qty = to_qty(min(position.qty, (-delta) / quote.price))
                if qty <= 0:
                    continue
                out.append(ProspectiveTrade(symbol, "sell", qty, quote.price))
        return out

    def _cancel_draft_orders(
        self, account_id: str, approval_id: str, reason: str
    ) -> None:
        """Cancel the draft orders a propose() created when the approval is
        rejected or expires: drafts never execute on their own."""
        for order in self._orders.list_for_approval(account_id, approval_id):
            if order.status not in TERMINAL_STATUSES:
                self._orders.cancel(order.id, reason)
                self._audit.append(
                    actor=self._agent_name,
                    action="order.cancelled",
                    account_id=account_id,
                    details={"order_id": order.id, "reason": reason},
                )

    def _execute_trades(
        self,
        account_id: str,
        prospective: list[ProspectiveTrade],
        orders: list[Order] | None = None,
    ) -> list[TradeRecord]:
        """Execute planned trades through the order lifecycle.

        ``orders`` carries the draft orders a propose() created (human-gated
        path); without them this is the legacy direct path, where each trade
        is auto-authorized by the system. Every trade gets a full lifecycle
        record: draft -> awaiting_authorization|submitted -> filled, or
        rejected on limit breaches and execution errors. Mock fills are
        recorded with ``simulated=True``.
        """
        account = self._store.get_account(account_id)
        account_mode = account.mode if account else Mode.EXPERIMENTAL
        # Match draft orders to prospective trades by economics, not by
        # position: both lists are in propose() order, but an explicit match
        # keeps a store reordering from misassigning them.
        unmatched = list(orders) if orders else []

        def take_order(t: ProspectiveTrade) -> Order:
            for i, o in enumerate(unmatched):
                if (
                    o.symbol == t.symbol
                    and o.side == t.side
                    and o.qty == t.qty
                    and o.status not in TERMINAL_STATUSES
                ):
                    return unmatched.pop(i)
            created, _ = self._orders.create(
                account_id=account_id,
                symbol=t.symbol,
                side=t.side,
                qty=t.qty,
                mode=account_mode,
                simulated=True,
            )
            return created

        trades: list[TradeRecord] = []
        for t in prospective:
            order = take_order(t)
            try:
                if orders is not None:
                    # human-gated path: explicit authorization, then submit
                    order = self._orders.authorize(
                        order.id, est_price=t.est_price,
                        limits=self._risk_limits,
                    )
                    order = self._orders.submit(order.id)
                else:
                    # direct path: system auto-authorizes (draft -> submitted)
                    order = self._orders.authorize_direct(
                        order.id, est_price=t.est_price,
                        limits=self._risk_limits,
                    )
            except RiskLimitBreach as breach:
                self._orders.reject(order.id, breach.reason)
                self._audit.append(
                    actor=self._agent_name,
                    action="trade.skipped",
                    account_id=account_id,
                    outcome="rejected",
                    details={
                        "symbol": t.symbol,
                        "order_id": order.id,
                        "reason": breach.reason,
                        "limit": breach.limit,
                    },
                )
                continue
            try:
                if t.side == "buy":
                    txn = execute_paper_buy(
                        self._store, account_id, t.symbol, t.qty, t.est_price,
                        mode=account_mode, order_id=order.id,
                    )
                else:
                    txn = execute_paper_sell(
                        self._store, account_id, t.symbol, t.qty, t.est_price,
                        mode=account_mode, order_id=order.id,
                    )
            except (InsufficientFundsError, InsufficientPositionError) as exc:
                self._orders.reject(order.id, str(exc))
                self._events.append(
                    self._agent_name,
                    f"{self._agent_name}.trade_skipped",
                    {"symbol": t.symbol, "reason": str(exc)},
                )
                self._audit.append(
                    actor=self._agent_name,
                    action="trade.skipped",
                    account_id=account_id,
                    outcome="rejected",
                    details={
                        "symbol": t.symbol,
                        "order_id": order.id,
                        "reason": str(exc),
                    },
                )
                continue
            self._orders.record_fill(
                order.id,
                filled_qty=t.qty,
                avg_fill_price=txn.price,
                simulated=True,  # mock fill: never a real execution record
            )
            trades.append(
                TradeRecord(
                    side=txn.side,
                    symbol=t.symbol,
                    quantity=qty_str(txn.qty),
                    price=qty_str(txn.price),
                )
            )
            self._events.append(
                self._agent_name,
                f"{self._agent_name}.trade_executed",
                {
                    "side": txn.side,
                    "symbol": t.symbol,
                    "quantity": str(txn.qty),
                    "price": str(txn.price),
                    "order_id": order.id,
                    "simulated": True,
                },
            )
            self._audit.append(
                actor=self._agent_name,
                action="trade.executed",
                account_id=account_id,
                details={
                    "symbol": t.symbol,
                    "side": txn.side,
                    "qty": str(txn.qty),
                    "price": str(txn.price),
                    "order_id": order.id,
                    "simulated": True,
                },
            )
        return trades

    async def _snapshot(self, account_id: str) -> None:
        account = self._store.get_account(account_id)
        positions = self._store.get_positions(account_id)
        quotes = {}
        for pos in positions:
            try:
                quotes[pos.symbol] = await self._market.get_quote(pos.symbol)
            except CreditsExhausted:
                raise
            except (MarketDataError, ProviderError):
                continue
        pv = value_portfolio(account, positions, quotes)
        self._store.add_snapshot(
            Snapshot(
                account_id=account_id,
                total_value=pv.total_value,
                cash=account.cash,
                created_at=utcnow(),
            )
        )
