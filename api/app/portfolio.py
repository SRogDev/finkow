"""Portfolio valuation: average cost, P&L, allocation, returns.

All money stays Decimal. Allocation weights always sum to exactly 1.0000
(the last bucket absorbs rounding dust).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from app.market import Quote
from app.money import ALLOC_QUANTUM, to_cash
from app.store import Account, Position


@dataclass
class PositionView:
    symbol: str
    qty: Decimal
    avg_cost: Decimal
    price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    stale: bool


@dataclass
class PortfolioView:
    account_id: str
    cash: Decimal
    initial_cash: Decimal
    positions: list[PositionView]
    total_value: Decimal
    total_return: Decimal
    total_return_pct: Decimal
    allocation: dict[str, Decimal]
    as_of: datetime


def average_cost(
    old_qty: Decimal, old_avg: Decimal, buy_qty: Decimal, buy_price: Decimal
) -> Decimal:
    """Volume-weighted average cost after a buy."""
    if buy_qty <= 0:
        raise ValueError("buy quantity must be positive")
    if old_qty == 0:
        return to_cash(buy_price)
    total_qty = old_qty + buy_qty
    return to_cash((old_qty * old_avg + buy_qty * buy_price) / total_qty)


def unrealized_pnl(qty: Decimal, avg_cost: Decimal, price: Decimal) -> Decimal:
    return to_cash(qty * (price - avg_cost))


def allocation(market_values: dict[str, Decimal], cash: Decimal) -> dict[str, Decimal]:
    """Weight per symbol + CASH, summing to exactly 1.0000."""
    buckets = list(market_values.items()) + [("CASH", cash)]
    total = sum((v for _, v in buckets), Decimal("0"))
    if total == 0:
        return {"CASH": Decimal("1.0000")}
    weights = [
        (sym, (value / total).quantize(ALLOC_QUANTUM, rounding=ROUND_HALF_UP))
        for sym, value in buckets
    ]
    # Last bucket absorbs rounding so weights sum to exactly 1.
    fixed = sum((w for _, w in weights[:-1]), Decimal("0"))
    last_sym, _ = weights[-1]
    weights[-1] = (last_sym, (Decimal("1") - fixed).quantize(ALLOC_QUANTUM))
    return dict(weights)


def total_return_pct(total_value: Decimal, initial: Decimal) -> Decimal:
    if initial == 0:
        return Decimal("0.00")
    return to_cash((total_value - initial) / initial * Decimal("100"))


def value_portfolio(
    account: Account, positions: list[Position], quotes: dict[str, Quote]
) -> PortfolioView:
    """Value every position at its quote; fall back to avg_cost (stale) when missing."""
    views: list[PositionView] = []
    market_values: dict[str, Decimal] = {}
    for pos in positions:
        quote = quotes.get(pos.symbol)
        price = quote.price if quote else pos.avg_cost
        stale = quote.stale if quote else True
        market_value = to_cash(pos.qty * price)
        pnl = unrealized_pnl(pos.qty, pos.avg_cost, price)
        cost_basis = pos.qty * pos.avg_cost
        pnl_pct = to_cash(pnl / cost_basis * Decimal("100")) if cost_basis else Decimal("0.00")
        views.append(
            PositionView(
                symbol=pos.symbol,
                qty=pos.qty,
                avg_cost=pos.avg_cost,
                price=price,
                market_value=market_value,
                unrealized_pnl=pnl,
                unrealized_pnl_pct=pnl_pct,
                stale=stale,
            )
        )
        market_values[pos.symbol] = market_value
    total_value = to_cash(account.cash + sum(market_values.values(), Decimal("0")))
    return PortfolioView(
        account_id=account.id,
        cash=account.cash,
        initial_cash=account.initial_cash,
        positions=views,
        total_value=total_value,
        total_return=to_cash(total_value - account.initial_cash),
        total_return_pct=total_return_pct(total_value, account.initial_cash),
        allocation=allocation(market_values, account.cash),
        as_of=datetime.now(UTC),
    )
