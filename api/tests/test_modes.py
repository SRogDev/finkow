"""Mode separation: Real vs Experimental must never share state.

Domain invariant (SPEC S8/S9): no operation may read or mutate state across
modes. Real mode has no execution path wired: every real execution attempt
must raise a clear "not configured" error, never silently fall back to mock.
"""

from decimal import Decimal

import pytest

from app.brokerage import LiveTradingDisabledError, MockBrokerage, OrderSide
from app.modes import (
    REAL_NOT_CONFIGURED,
    CrossModeError,
    Mode,
    check_mode,
    coerce_mode,
)
from app.store import STARTING_CASH, InMemoryStore
from app.trading import execute_paper_buy, execute_paper_sell


def _account(store: InMemoryStore, mode: Mode = Mode.EXPERIMENTAL):
    return store.create_account(email=None, initial_cash=STARTING_CASH,
                                owner_user_id="u1", mode=mode)


def test_mode_values():
    assert Mode.REAL.value == "real"
    assert Mode.EXPERIMENTAL.value == "experimental"


def test_coerce_mode():
    assert coerce_mode("real") is Mode.REAL
    assert coerce_mode("experimental") is Mode.EXPERIMENTAL
    assert coerce_mode("REAL") is Mode.REAL
    with pytest.raises(ValueError):
        coerce_mode("paper")


def test_check_mode_same_ok():
    check_mode(Mode.EXPERIMENTAL, Mode.EXPERIMENTAL, "test")


def test_check_mode_mismatch_raises():
    with pytest.raises(CrossModeError):
        check_mode(Mode.REAL, Mode.EXPERIMENTAL, "holdings")


def test_experimental_trade_works():
    store = InMemoryStore()
    acct = _account(store)
    txn = execute_paper_buy(store, acct.id, "AAPL", Decimal("10"),
                            Decimal("150.00"), mode=Mode.EXPERIMENTAL)
    assert txn.mode is Mode.EXPERIMENTAL
    pos = store.get_position(acct.id, "AAPL")
    assert pos is not None and pos.mode is Mode.EXPERIMENTAL


def test_experimental_op_on_real_account_is_contamination():
    """An experimental order must never touch a real-mode account."""
    store = InMemoryStore()
    acct = _account(store, mode=Mode.REAL)
    with pytest.raises(CrossModeError):
        execute_paper_buy(store, acct.id, "AAPL", Decimal("10"),
                          Decimal("150.00"), mode=Mode.EXPERIMENTAL)
    # Nothing moved.
    assert store.get_account(acct.id).cash == STARTING_CASH
    assert store.get_position(acct.id, "AAPL") is None


def test_real_op_on_experimental_account_is_contamination():
    """A real-mode operation must never touch experimental holdings."""
    store = InMemoryStore()
    acct = _account(store, mode=Mode.EXPERIMENTAL)
    with pytest.raises(CrossModeError):
        execute_paper_buy(store, acct.id, "AAPL", Decimal("10"),
                          Decimal("150.00"), mode=Mode.REAL)
    assert store.get_account(acct.id).cash == STARTING_CASH


def test_real_execution_is_never_silently_mocked():
    """Real mode has no execution path: clear error, no fallback, no state."""
    store = InMemoryStore()
    acct = _account(store, mode=Mode.REAL)
    with pytest.raises(LiveTradingDisabledError) as exc:
        execute_paper_buy(store, acct.id, "AAPL", Decimal("10"),
                          Decimal("150.00"), mode=Mode.REAL)
    assert REAL_NOT_CONFIGURED in str(exc.value)
    assert store.get_account(acct.id).cash == STARTING_CASH
    assert store.get_position(acct.id, "AAPL") is None
    assert store.list_transactions(acct.id) == []


def test_real_sell_also_blocked():
    store = InMemoryStore()
    acct = _account(store, mode=Mode.REAL)
    with pytest.raises(LiveTradingDisabledError):
        execute_paper_sell(store, acct.id, "AAPL", Decimal("10"),
                           Decimal("150.00"), mode=Mode.REAL)


def test_mock_brokerage_refuses_real_mode():
    """The mock brokerage must never simulate a real order."""
    import asyncio

    broker = MockBrokerage(mode=Mode.REAL)
    with pytest.raises(LiveTradingDisabledError) as exc:
        asyncio.run(broker.submit_order("AAPL", Decimal("1"), OrderSide.BUY))
    assert REAL_NOT_CONFIGURED in str(exc.value)


def test_mock_brokerage_experimental_orders_carry_mode():
    import asyncio

    broker = MockBrokerage(mode=Mode.EXPERIMENTAL)
    order = asyncio.run(
        broker.submit_order("AAPL", Decimal("1"), OrderSide.BUY))
    assert order.mode is Mode.EXPERIMENTAL


def test_submit_live_order_still_raises():
    from app.brokerage import OrderSide, submit_live_order

    with pytest.raises(LiveTradingDisabledError):
        submit_live_order("AAPL", Decimal("1"), OrderSide.BUY)
