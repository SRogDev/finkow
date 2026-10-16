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
from app.money import qty_str, to_cash, to_qty
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
        approval_ttl: timedelta = timedelta(minutes=15),
    ) -> None:
        self._store = store
        self._market = market
        self._events = events or EventLog()
        self._audit = audit or AuditLog()
        self._agent_name = agent_name
        self._max_trade_usd = max_trade_usd
        self._max_daily_trades = max_daily_trades
        self._approval_ttl = approval_ttl

    # ---------------------------------------------------------- live (disabled)

    def submit_live_order(self, symbol: str, qty: Decimal) -> None:
        """The live-trading path. Intentionally unwired — always raises."""
        raise LiveTradingDisabledError(
            "live trading is disabled: paper simulation only."
        )

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
            account_id=account_id, trades=trades, total_usd=total, status="pending"
        )
        self._store.save_approval(request)
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
        trades = self._execute_trades(request.account_id, prospective)
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

    def _execute_trades(
        self, account_id: str, prospective: list[ProspectiveTrade]
    ) -> list[TradeRecord]:
        """Execute planned trades, enforcing limits. Returns executed records."""
        trades: list[TradeRecord] = []
        for t in prospective:
            if t.est_value > self._max_trade_usd:
                self._audit.append(
                    actor=self._agent_name,
                    action="trade.skipped",
                    account_id=account_id,
                    outcome="rejected",
                    details={
                        "symbol": t.symbol,
                        "reason": f"exceeds max_trade_usd {self._max_trade_usd}",
                    },
                )
                continue
            if self._trades_today(account_id) >= self._max_daily_trades:
                self._audit.append(
                    actor=self._agent_name,
                    action="trade.skipped",
                    account_id=account_id,
                    outcome="rejected",
                    details={"symbol": t.symbol, "reason": "daily trade limit reached"},
                )
                continue
            try:
                if t.side == "buy":
                    txn = execute_paper_buy(
                        self._store, account_id, t.symbol, t.qty, t.est_price
                    )
                else:
                    txn = execute_paper_sell(
                        self._store, account_id, t.symbol, t.qty, t.est_price
                    )
            except (InsufficientFundsError, InsufficientPositionError) as exc:
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
                    details={"symbol": t.symbol, "reason": str(exc)},
                )
                continue
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
                },
            )
        return trades

    def _trades_today(self, account_id: str) -> int:
        today = datetime.now(UTC).date()
        return sum(
            1
            for t in self._store.list_transactions(account_id)
            if t.created_at.date() == today
        )

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
