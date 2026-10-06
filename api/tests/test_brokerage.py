"""Brokerage port: Alpaca-shaped paper-trading interface + mock adapter.

RED phase: pins the brokerage contract before implementation. The port is
shaped like Alpaca's paper-trading API (account, positions, market orders).
Live keys are Roger's later step — the mock adapter simulates fills so the
full investment flow verifies end to end today.

Compliance note: this interface executes simulated orders only. Connecting a
live brokerage needs real keys, local regulations, and explicit user opt-in —
none of which exist in v2.1.
"""

import asyncio
from decimal import Decimal

import pytest

from app.brokerage import (
    BrokerageOrder,
    BrokeragePort,
    LiveTradingDisabledError,
    MockBrokerage,
    OrderSide,
    submit_live_order,
)


def _run(coro):
    return asyncio.run(coro)


def _prices():
    return {"AAPL": Decimal("150.00"), "MSFT": Decimal("420.00")}


def test_mock_brokerage_account_starts_with_paper_cash():
    b = MockBrokerage(price_fn=lambda s: _prices()[s], starting_cash=Decimal("10000"))
    acct = _run(b.get_account())
    assert acct.cash == Decimal("10000.00")
    assert acct.portfolio_value == Decimal("10000.00")
    assert acct.live is False


def test_mock_brokerage_market_order_fills_immediately():
    b = MockBrokerage(price_fn=lambda s: _prices()[s], starting_cash=Decimal("10000"))
    order = _run(
        b.submit_order(symbol="AAPL", qty=Decimal("10"), side=OrderSide.BUY)
    )
    assert isinstance(order, BrokerageOrder)
    assert order.status == "filled"
    assert order.filled_price == Decimal("150.00")
    acct = _run(b.get_account())
    assert acct.cash == Decimal("8500.00")
    positions = _run(b.get_positions())
    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"
    assert positions[0].qty == Decimal("10")


def test_mock_brokerage_sell_reduces_position():
    b = MockBrokerage(price_fn=lambda s: _prices()[s], starting_cash=Decimal("10000"))
    _run(b.submit_order(symbol="AAPL", qty=Decimal("10"), side=OrderSide.BUY))
    order = _run(b.submit_order(symbol="AAPL", qty=Decimal("4"), side=OrderSide.SELL))
    assert order.status == "filled"
    positions = _run(b.get_positions())
    assert positions[0].qty == Decimal("6")
    assert _run(b.get_account()).cash == Decimal("9100.00")


def test_mock_brokerage_rejects_insufficient_funds_and_position():
    b = MockBrokerage(price_fn=lambda s: _prices()[s], starting_cash=Decimal("100"))
    with pytest.raises(ValueError, match="insufficient"):
        _run(b.submit_order(symbol="AAPL", qty=Decimal("10"), side=OrderSide.BUY))
    with pytest.raises(ValueError, match="insufficient"):
        _run(b.submit_order(symbol="MSFT", qty=Decimal("1"), side=OrderSide.SELL))


def test_mock_brokerage_order_lifecycle_queryable():
    b = MockBrokerage(price_fn=lambda s: _prices()[s])
    order = _run(b.submit_order(symbol="MSFT", qty=Decimal("2"), side=OrderSide.BUY))
    fetched = _run(b.get_order(order.id))
    assert fetched is not None and fetched.id == order.id
    assert _run(b.get_order("nope")) is None
    orders = _run(b.list_orders())
    assert [o.id for o in orders] == [order.id]


def test_mock_brokerage_rejects_unknown_symbol():
    b = MockBrokerage(price_fn=lambda s: _prices()[s])
    with pytest.raises(ValueError, match="unknown symbol"):
        _run(b.submit_order(symbol="NOPEXYZ", qty=Decimal("1"), side=OrderSide.BUY))


def test_live_trading_path_is_disabled():
    with pytest.raises(LiveTradingDisabledError):
        submit_live_order(
            symbol="AAPL", qty=Decimal("1"), side=OrderSide.BUY, api_key="anything"
        )


def test_brokerage_port_is_a_protocol():
    assert isinstance(MockBrokerage(price_fn=lambda s: Decimal("1")), BrokeragePort)
