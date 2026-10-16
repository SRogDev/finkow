"""Order lifecycle: explicit states, validated transitions, idempotency,
reconciliation, and persistence across store backends."""

from decimal import Decimal

import pytest

from app.brokerage import LiveTradingDisabledError
from app.modes import Mode
from app.orders import (
    TERMINAL_STATUSES,
    IllegalOrderTransitionError,
    OrderLifecycle,
    OrderStatus,
    ReconciliationReport,
    RiskLimitBreach,
    RiskLimits,
    transition,
)
from app.storage_sqlite import SqliteBackend, SqliteStore
from app.store import InMemoryStore


def _store() -> InMemoryStore:
    return InMemoryStore()


def _account(store: InMemoryStore, mode: Mode = Mode.EXPERIMENTAL):
    return store.create_account(
        email=None, initial_cash=Decimal("100000"), mode=mode
    )


def _lifecycle(store: InMemoryStore) -> OrderLifecycle:
    return OrderLifecycle(store)


# ---------------------------------------------------------------- enum & map


def test_order_status_values_are_stable_strings():
    assert OrderStatus.DRAFT.value == "draft"
    assert OrderStatus.AWAITING_AUTHORIZATION.value == "awaiting_authorization"
    assert OrderStatus.SUBMITTED.value == "submitted"
    assert OrderStatus.PARTIALLY_FILLED.value == "partially_filled"
    assert OrderStatus.FILLED.value == "filled"
    assert OrderStatus.REJECTED.value == "rejected"
    assert OrderStatus.CANCELLED.value == "cancelled"
    assert OrderStatus.FAILED.value == "failed"


def test_every_status_has_a_transition_entry_and_terminals_are_closed():
    assert set(OrderStatus) == {
        OrderStatus.DRAFT,
        OrderStatus.AWAITING_AUTHORIZATION,
        OrderStatus.SUBMITTED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
        OrderStatus.FAILED,
    }
    for status in TERMINAL_STATUSES:
        assert status in (
            OrderStatus.FILLED,
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
            OrderStatus.FAILED,
        )


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        (OrderStatus.DRAFT, OrderStatus.AWAITING_AUTHORIZATION),
        (OrderStatus.DRAFT, OrderStatus.SUBMITTED),  # auto/system-authorized path
        (OrderStatus.DRAFT, OrderStatus.REJECTED),
        (OrderStatus.DRAFT, OrderStatus.CANCELLED),
        (OrderStatus.AWAITING_AUTHORIZATION, OrderStatus.SUBMITTED),
        (OrderStatus.AWAITING_AUTHORIZATION, OrderStatus.REJECTED),
        (OrderStatus.AWAITING_AUTHORIZATION, OrderStatus.CANCELLED),
        (OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED),
        (OrderStatus.SUBMITTED, OrderStatus.FILLED),
        (OrderStatus.SUBMITTED, OrderStatus.REJECTED),
        (OrderStatus.SUBMITTED, OrderStatus.CANCELLED),
        (OrderStatus.SUBMITTED, OrderStatus.FAILED),
        (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED),
        (OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCELLED),
        (OrderStatus.PARTIALLY_FILLED, OrderStatus.FAILED),
    ],
)
def test_legal_transitions_pass(from_status, to_status):
    transition(from_status, to_status)  # must not raise


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        (OrderStatus.DRAFT, OrderStatus.FILLED),  # cannot skip submission
        (OrderStatus.DRAFT, OrderStatus.PARTIALLY_FILLED),
        (OrderStatus.AWAITING_AUTHORIZATION, OrderStatus.FILLED),
        (OrderStatus.AWAITING_AUTHORIZATION, OrderStatus.DRAFT),  # no going back
        (OrderStatus.SUBMITTED, OrderStatus.DRAFT),
        (OrderStatus.SUBMITTED, OrderStatus.AWAITING_AUTHORIZATION),
        (OrderStatus.FILLED, OrderStatus.CANCELLED),  # terminals are immutable
        (OrderStatus.FILLED, OrderStatus.SUBMITTED),
        (OrderStatus.REJECTED, OrderStatus.SUBMITTED),
        (OrderStatus.CANCELLED, OrderStatus.FILLED),
        (OrderStatus.FAILED, OrderStatus.SUBMITTED),
    ],
)
def test_illegal_transitions_raise(from_status, to_status):
    with pytest.raises(IllegalOrderTransitionError):
        transition(from_status, to_status)


# ---------------------------------------------------------------- lifecycle


def test_create_starts_in_draft():
    store, account = _store(), None
    account = _account(store)
    order, created = _lifecycle(store).create(
        account_id=account.id, symbol="AAPL", side="buy",
        qty=Decimal("10"), mode=account.mode,
    )
    assert created is True
    assert order.status == OrderStatus.DRAFT
    assert store.get_order(order.id) is not None


def test_create_rejects_nonpositive_qty_and_bad_side():
    store = _store()
    account = _account(store)
    lc = _lifecycle(store)
    with pytest.raises(ValueError, match="quantity must be positive"):
        lc.create(account_id=account.id, symbol="AAPL", side="buy",
                  qty=Decimal("0"), mode=account.mode)
    with pytest.raises(ValueError, match="side must be"):
        lc.create(account_id=account.id, symbol="AAPL", side="hold",
                  qty=Decimal("1"), mode=account.mode)


def test_create_in_real_mode_never_simulates():
    store = _store()
    account = _account(store, mode=Mode.REAL)
    with pytest.raises(LiveTradingDisabledError):
        _lifecycle(store).create(
            account_id=account.id, symbol="AAPL", side="buy",
            qty=Decimal("1"), mode=Mode.REAL,
        )


def test_full_mock_lifecycle_draft_to_filled():
    store = _store()
    account = _account(store)
    lc = _lifecycle(store)
    order, _ = lc.create(
        account_id=account.id, symbol="AAPL", side="buy",
        qty=Decimal("10"), mode=account.mode, simulated=True,
    )
    order = lc.authorize(order.id)
    assert order.status == OrderStatus.AWAITING_AUTHORIZATION
    order = lc.submit(order.id)
    assert order.status == OrderStatus.SUBMITTED
    order = lc.record_fill(
        order.id, filled_qty=Decimal("10"), avg_fill_price=Decimal("150"),
        simulated=True,
    )
    assert order.status == OrderStatus.FILLED
    assert order.simulated is True
    assert order.provider_order_id is None  # mock has no provider order id
    assert order.filled_qty == Decimal("10")


def test_partial_fill_then_fill():
    store = _store()
    account = _account(store)
    lc = _lifecycle(store)
    order, _ = lc.create(
        account_id=account.id, symbol="AAPL", side="buy",
        qty=Decimal("10"), mode=account.mode,
    )
    lc.submit(order.id)
    order = lc.record_partial_fill(
        order.id, filled_qty=Decimal("4"), avg_fill_price=Decimal("150")
    )
    assert order.status == OrderStatus.PARTIALLY_FILLED
    assert order.filled_qty == Decimal("4")
    order = lc.record_fill(
        order.id, filled_qty=Decimal("10"), avg_fill_price=Decimal("151")
    )
    assert order.status == OrderStatus.FILLED


def test_reject_cancel_fail_record_reasons():
    store = _store()
    account = _account(store)
    lc = _lifecycle(store)
    o1, _ = lc.create(account_id=account.id, symbol="A", side="buy",
                      qty=Decimal("1"), mode=account.mode)
    o1 = lc.reject(o1.id, "exceeds max_trade_usd")
    assert o1.status == OrderStatus.REJECTED
    assert o1.reject_reason == "exceeds max_trade_usd"
    o2, _ = lc.create(account_id=account.id, symbol="B", side="buy",
                      qty=Decimal("1"), mode=account.mode)
    o2 = lc.cancel(o2.id, "human rejected")
    assert o2.status == OrderStatus.CANCELLED
    o3, _ = lc.create(account_id=account.id, symbol="C", side="buy",
                      qty=Decimal("1"), mode=account.mode)
    lc.submit(o3.id)
    o3 = lc.fail(o3.id, "provider timeout, status unknown")
    assert o3.status == OrderStatus.FAILED


def test_terminal_orders_are_immutable():
    store = _store()
    account = _account(store)
    lc = _lifecycle(store)
    order, _ = lc.create(account_id=account.id, symbol="A", side="buy",
                         qty=Decimal("1"), mode=account.mode)
    lc.submit(order.id)
    order = lc.record_fill(order.id, filled_qty=Decimal("1"),
                           avg_fill_price=Decimal("10"))
    for op in (
        lambda: lc.authorize(order.id),
        lambda: lc.submit(order.id),
        lambda: lc.cancel(order.id, "x"),
        lambda: lc.reject(order.id, "x"),
        lambda: lc.fail(order.id, "x"),
    ):
        with pytest.raises(IllegalOrderTransitionError):
            op()


# ---------------------------------------------------------------- idempotency


def test_idempotent_create_returns_original_order():
    store = _store()
    account = _account(store)
    lc = _lifecycle(store)
    first, created_first = lc.create(
        account_id=account.id, symbol="AAPL", side="buy", qty=Decimal("10"),
        mode=account.mode, idempotency_key="key-123",
    )
    second, created_second = lc.create(
        account_id=account.id, symbol="AAPL", side="buy", qty=Decimal("10"),
        mode=account.mode, idempotency_key="key-123",
    )
    assert created_first is True
    assert created_second is False
    assert second.id == first.id
    assert len(store.list_orders(account.id)) == 1  # no duplicate


def test_idempotency_key_is_scoped_per_account():
    store = _store()
    a1, a2 = _account(store), _account(store)
    lc = _lifecycle(store)
    o1, _ = lc.create(account_id=a1.id, symbol="A", side="buy", qty=Decimal("1"),
                      mode=a1.mode, idempotency_key="k")
    o2, _ = lc.create(account_id=a2.id, symbol="A", side="buy", qty=Decimal("1"),
                      mode=a2.mode, idempotency_key="k")
    assert o1.id != o2.id


def test_idempotency_survives_replay_after_fill():
    store = _store()
    account = _account(store)
    lc = _lifecycle(store)
    first, _ = lc.create(account_id=account.id, symbol="AAPL", side="buy",
                         qty=Decimal("2"), mode=account.mode,
                         idempotency_key="replay-me")
    lc.submit(first.id)
    lc.record_fill(first.id, filled_qty=Decimal("2"),
                   avg_fill_price=Decimal("150"))
    again, created = lc.create(account_id=account.id, symbol="AAPL", side="buy",
                               qty=Decimal("2"), mode=account.mode,
                               idempotency_key="replay-me")
    assert created is False
    assert again.id == first.id
    assert again.status == OrderStatus.FILLED


# ---------------------------------------------------------------- risk checks


def test_authorize_enforces_max_trade_usd():
    store = _store()
    account = _account(store)
    lc = _lifecycle(store)
    order, _ = lc.create(account_id=account.id, symbol="AAPL", side="buy",
                         qty=Decimal("1000"), mode=account.mode)
    with pytest.raises(RiskLimitBreach, match="max_trade_usd"):
        lc.authorize(
            order.id, est_price=Decimal("150"),
            limits=RiskLimits(max_trade_usd=Decimal("25000")),
        )
    # breach does not transition: still draft
    assert store.get_order(order.id).status == OrderStatus.DRAFT


def test_authorize_enforces_daily_account_limit():
    store = _store()
    account = _account(store)
    lc = _lifecycle(store)
    limits = RiskLimits(max_daily_trades_per_account=1)
    o1, _ = lc.create(account_id=account.id, symbol="A", side="buy",
                      qty=Decimal("1"), mode=account.mode)
    lc.authorize(o1.id, est_price=Decimal("10"), limits=limits)
    lc.submit(o1.id)
    lc.record_fill(o1.id, filled_qty=Decimal("1"), avg_fill_price=Decimal("10"))
    # second trade today breaches the account daily limit
    o2, _ = lc.create(account_id=account.id, symbol="B", side="buy",
                      qty=Decimal("1"), mode=account.mode)
    with pytest.raises(RiskLimitBreach, match="daily"):
        lc.authorize(o2.id, est_price=Decimal("10"), limits=limits)


def test_authorize_enforces_daily_user_limit_across_accounts():
    store = _store()
    owner = "user-1"
    a1 = store.create_account(email=None, initial_cash=Decimal("100000"),
                              owner_user_id=owner)
    a2 = store.create_account(email=None, initial_cash=Decimal("100000"),
                              owner_user_id=owner)
    lc = _lifecycle(store)
    limits = RiskLimits(max_daily_trades_per_user=1)
    o1, _ = lc.create(account_id=a1.id, symbol="A", side="buy",
                      qty=Decimal("1"), mode=a1.mode)
    lc.authorize(o1.id, est_price=Decimal("10"), limits=limits)
    lc.submit(o1.id)
    lc.record_fill(o1.id, filled_qty=Decimal("1"), avg_fill_price=Decimal("10"))
    # one trade already happened today for this user -> second account blocked
    o2, _ = lc.create(account_id=a2.id, symbol="B", side="buy",
                      qty=Decimal("1"), mode=a2.mode)
    with pytest.raises(RiskLimitBreach, match="daily"):
        lc.authorize(o2.id, est_price=Decimal("10"), limits=limits)


# ---------------------------------------------------------------- reconcile


def test_reconcile_rereads_recorded_state():
    store = _store()
    account = _account(store)
    lc = _lifecycle(store)
    order, _ = lc.create(account_id=account.id, symbol="AAPL", side="buy",
                         qty=Decimal("5"), mode=account.mode)
    # mutate the store directly behind the lifecycle's back
    stored = store.get_order(order.id)
    stored.status = OrderStatus.CANCELLED
    store.save_order(stored)
    report = lc.reconcile(order.id)
    assert isinstance(report, ReconciliationReport)
    assert report.recorded_status == OrderStatus.CANCELLED
    assert report.consistent is True  # terminal cancelled: nothing to do


def test_reconcile_filled_order_checks_linked_fill():
    store = _store()
    account = _account(store)
    lc = _lifecycle(store)
    order, _ = lc.create(account_id=account.id, symbol="AAPL", side="buy",
                         qty=Decimal("5"), mode=account.mode)
    lc.submit(order.id)
    lc.record_fill(order.id, filled_qty=Decimal("5"),
                   avg_fill_price=Decimal("150"))
    report = lc.reconcile(order.id)
    assert report.consistent is True
    assert report.simulated is True
    assert any("simulated" in note.lower() for note in report.notes)


def test_reconcile_open_order_does_not_assume_failure():
    """A timeout does NOT prove failure: reconcile flags the order for
    provider inquiry instead of marking it failed."""
    store = _store()
    account = _account(store)
    lc = _lifecycle(store)
    order, _ = lc.create(account_id=account.id, symbol="AAPL", side="buy",
                         qty=Decimal("5"), mode=account.mode)
    lc.submit(order.id)  # stuck in submitted: no fill recorded (mock fills sync)
    report = lc.reconcile(order.id)
    assert report.consistent is False
    assert report.recorded_status == OrderStatus.SUBMITTED
    joined = " ".join(report.notes).lower()
    assert "does not prove failure" in joined or "timeout" in joined
    assert report.action_required  # a human/system must investigate


def test_reconcile_unknown_order_raises():
    with pytest.raises(ValueError, match="order not found"):
        _lifecycle(_store()).reconcile("nope")


# ---------------------------------------------------------------- transactions


def test_paper_fill_transaction_links_order_and_marks_simulated():
    from app.trading import execute_paper_buy

    store = _store()
    account = _account(store)
    lc = _lifecycle(store)
    order, _ = lc.create(account_id=account.id, symbol="AAPL", side="buy",
                         qty=Decimal("2"), mode=account.mode)
    lc.submit(order.id)
    txn = execute_paper_buy(store, account.id, "AAPL", Decimal("2"),
                            Decimal("150"), mode=account.mode,
                            order_id=order.id)
    lc.record_fill(order.id, filled_qty=Decimal("2"),
                   avg_fill_price=Decimal("150"))
    assert txn.order_id == order.id
    assert txn.status == OrderStatus.FILLED
    assert txn.simulated is True


# ---------------------------------------------------------------- sqlite


def test_orders_persist_across_sqlite_backends(tmp_path):
    db = tmp_path / "finkow.db"
    backend = SqliteBackend(db)
    store = SqliteStore(backend)
    account = store.create_account(email=None, initial_cash=Decimal("100000"))
    lc = OrderLifecycle(store)
    order, created = lc.create(
        account_id=account.id, symbol="AAPL", side="buy", qty=Decimal("3"),
        mode=account.mode, idempotency_key="persist-key",
    )
    assert created is True
    lc.submit(order.id)
    lc.record_fill(order.id, filled_qty=Decimal("3"),
                   avg_fill_price=Decimal("150"))
    backend.close()

    # fresh backend on the same file: the order survives the restart
    store2 = SqliteStore(SqliteBackend(db))
    again = store2.get_order(order.id)
    assert again is not None
    assert again.status == OrderStatus.FILLED
    assert again.simulated is True
    assert again.filled_qty == Decimal("3")
    assert again.avg_fill_price == Decimal("150")
    replay = store2.get_order_by_idempotency_key(account.id, "persist-key")
    assert replay is not None and replay.id == order.id
    assert [o.id for o in store2.list_orders(account.id)] == [order.id]
    assert [a.id for a in store2.list_accounts_by_owner("")] == [account.id]
