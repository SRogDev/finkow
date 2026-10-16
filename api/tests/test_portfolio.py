"""Portfolio math: average cost, P&L, allocation, returns — all Decimal-exact."""

from datetime import UTC, datetime
from decimal import Decimal

from app.market import Quote
from app.portfolio import (
    allocation,
    average_cost,
    total_return_pct,
    unrealized_pnl,
    value_portfolio,
)
from app.store import Account, Position


def test_average_cost_weighted():
    # 10 @ 150, then 10 @ 170 -> avg 160
    assert average_cost(Decimal("10"), Decimal("150"), Decimal("10"), Decimal("170")) == Decimal(
        "160.00"
    )


def test_average_cost_first_buy():
    assert average_cost(Decimal("0"), Decimal("0"), Decimal("5"), Decimal("99.99")) == Decimal(
        "99.99"
    )


def test_unrealized_pnl_long():
    assert unrealized_pnl(Decimal("10"), Decimal("150.00"), Decimal("160.00")) == Decimal("100.00")
    assert unrealized_pnl(Decimal("10"), Decimal("150.00"), Decimal("140.00")) == Decimal("-100.00")


def test_allocation_sums_to_one():
    alloc = allocation({"AAPL": Decimal("1500"), "BTC": Decimal("30000")}, Decimal("68500"))
    assert sum(alloc.values()) == Decimal("1.0000")
    assert alloc["BTC"] == Decimal("0.3000")
    assert alloc["CASH"] == Decimal("0.6850")


def test_allocation_empty_portfolio_is_all_cash():
    assert allocation({}, Decimal("100000")) == {"CASH": Decimal("1.0000")}


def test_total_return_pct():
    assert total_return_pct(Decimal("103000"), Decimal("100000")) == Decimal("3.00")
    assert total_return_pct(Decimal("95000"), Decimal("100000")) == Decimal("-5.00")


def _quote(symbol: str, price: str) -> Quote:
    return Quote(
        symbol=symbol,
        price=Decimal(price),
        currency="USD",
        as_of=datetime.now(UTC),
        provider="test",
    )


def test_value_portfolio_end_to_end():
    account = Account(
        id="a1",
        email=None,
        cash=Decimal("68500.00"),
        initial_cash=Decimal("100000.00"),
        created_at=datetime.now(UTC),
    )
    positions = [
        Position(account_id="a1", symbol="AAPL", qty=Decimal("10"), avg_cost=Decimal("150.00")),
        Position(account_id="a1", symbol="BTC", qty=Decimal("0.5"), avg_cost=Decimal("60000.00")),
    ]
    quotes = {"AAPL": _quote("AAPL", "160.00"), "BTC": _quote("BTC", "66000.00")}
    pv = value_portfolio(account, positions, quotes)
    assert pv.total_value == Decimal("103100.00")  # 68500 + 1600 + 33000
    assert pv.total_return_pct == Decimal("3.10")
    aapl = next(p for p in pv.positions if p.symbol == "AAPL")
    assert aapl.market_value == Decimal("1600.00")
    assert aapl.unrealized_pnl == Decimal("100.00")
    assert pv.allocation["BTC"] == (Decimal("33000") / Decimal("103100")).quantize(
        Decimal("0.0001")
    )
