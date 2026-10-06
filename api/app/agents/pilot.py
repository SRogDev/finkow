"""PortfolioPilot: paper-trade execution and rebalancing on v1 accounts.

Takes target allocations (symbol -> weight of total portfolio value) and moves
a virtual account toward them: buys underweight positions, sells overweight
ones. Every trade goes through ``app.trading`` — the same math as the v1
order endpoint — and every step is logged to the event log. Paper money only.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.agents.events import EventLog
from app.agents.planner import Allocation
from app.market import MarketDataError
from app.money import qty_str, to_cash, to_qty
from app.portfolio import value_portfolio
from app.ports import MarketDataPort, ProviderError
from app.store import InMemoryStore, Snapshot, utcnow
from app.trading import (
    InsufficientFundsError,
    InsufficientPositionError,
    execute_paper_buy,
    execute_paper_sell,
)

# Below this dollar distance from target we call it "close enough".
_DUST = Decimal("1.00")


@dataclass(frozen=True)
class TradeRecord:
    side: str
    symbol: str
    quantity: str
    price: str


@dataclass(frozen=True)
class InvestResult:
    account_id: str
    trades: list[TradeRecord]
    total_invested: Decimal


class PortfolioPilot:
    """Moves a virtual account toward target allocations (paper money)."""

    def __init__(
        self,
        store: InMemoryStore,
        market: MarketDataPort,
        events: EventLog | None = None,
    ) -> None:
        self._store = store
        self._market = market
        self._events = events or EventLog()

    async def invest(
        self, account_id: str, allocations: list[Allocation]
    ) -> InvestResult:
        account = self._store.get_account(account_id)
        if account is None:
            raise ValueError(f"account not found: {account_id}")
        targets = {a.symbol.upper().strip(): a.weight for a in allocations if a.weight > 0}
        if not targets:
            raise ValueError("no allocations to invest")
        self._events.append(
            "pilot",
            "pilot.invest_started",
            {"account_id": account_id, "targets": {s: str(w) for s, w in targets.items()}},
        )

        trades: list[TradeRecord] = []
        total_invested = Decimal("0")
        quotes = {}
        for symbol in targets:
            quotes[symbol] = await self._market.get_quote(symbol)
        pv = value_portfolio(account, self._store.get_positions(account_id), quotes)
        current_values = {p.symbol: p.market_value for p in pv.positions}

        for symbol, weight in targets.items():
            quote = quotes[symbol]
            if quote.price <= 0:
                continue
            target_value = to_cash(pv.total_value * weight)
            current = current_values.get(symbol, Decimal("0"))
            delta = target_value - current
            if abs(delta) < _DUST:
                continue
            try:
                if delta > 0:
                    qty = to_qty(delta / quote.price)
                    if qty <= 0:
                        continue
                    txn = execute_paper_buy(self._store, account_id, symbol, qty, quote.price)
                    total_invested += -txn.cash_delta
                else:
                    position = self._store.get_position(account_id, symbol)
                    if position is None:
                        continue
                    qty = to_qty(min(position.qty, (-delta) / quote.price))
                    if qty <= 0:
                        continue
                    txn = execute_paper_sell(self._store, account_id, symbol, qty, quote.price)
            except (InsufficientFundsError, InsufficientPositionError) as exc:
                self._events.append(
                    "pilot",
                    "pilot.trade_skipped",
                    {"symbol": symbol, "reason": str(exc)},
                )
                continue
            trades.append(
                TradeRecord(
                    side=txn.side,
                    symbol=symbol,
                    quantity=qty_str(txn.qty),
                    price=qty_str(txn.price),
                )
            )
            self._events.append(
                "pilot",
                "pilot.trade_executed",
                {
                    "side": txn.side,
                    "symbol": symbol,
                    "quantity": str(txn.qty),
                    "price": str(txn.price),
                },
            )

        self._events.append(
            "pilot",
            "pilot.invest_completed",
            {"account_id": account_id, "trades": len(trades)},
        )
        # Snapshot the batch so the portfolio keeps a pulse (history + explainer),
        # mirroring what the v1 order endpoint does per trade.
        final_positions = self._store.get_positions(account_id)
        final_quotes = {}
        for pos in final_positions:
            try:
                final_quotes[pos.symbol] = await self._market.get_quote(pos.symbol)
            except (MarketDataError, ProviderError):
                continue
        final_pv = value_portfolio(account, final_positions, final_quotes)
        self._store.add_snapshot(
            Snapshot(
                account_id=account_id,
                total_value=final_pv.total_value,
                cash=account.cash,
                created_at=utcnow(),
            )
        )
        return InvestResult(
            account_id=account_id, trades=trades, total_invested=to_cash(total_invested)
        )
