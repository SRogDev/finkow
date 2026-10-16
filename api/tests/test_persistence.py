"""Durable persistence: the SQLite store must survive restarts.

Financial history (accounts, positions, transactions), the audit log, the
agent event log, and the credits ledger must not be erased by a restart.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.billing.credits import CreditsLedger, InsufficientCredits
from app.modes import Mode
from app.storage_sqlite import (
    SqliteAuditLog,
    SqliteBackend,
    SqliteCreditsLedger,
    SqliteEventLog,
    SqliteStore,
)
from app.store import (
    STARTING_CASH,
    ApprovalRequest,
    Position,
    Snapshot,
    Transaction,
    UserProfile,
    new_id,
    utcnow,
)


@pytest.fixture()
def backend(tmp_path):
    b = SqliteBackend(tmp_path / "finkow.db")
    yield b
    b.close()


def test_store_round_trip(backend):
    store = SqliteStore(backend)
    acct = store.create_account(
        email="a@b.c", initial_cash=STARTING_CASH,
        owner_user_id="user-1", mode=Mode.EXPERIMENTAL,
    )
    assert acct.owner_user_id == "user-1"
    assert acct.mode is Mode.EXPERIMENTAL

    loaded = store.get_account(acct.id)
    assert loaded is not None
    assert loaded.cash == STARTING_CASH
    assert loaded.owner_user_id == "user-1"
    assert loaded.mode is Mode.EXPERIMENTAL

    store.upsert_position(Position(acct.id, "AAPL", Decimal("10"),
                                  Decimal("150.00"), mode=Mode.EXPERIMENTAL))
    pos = store.get_position(acct.id, "AAPL")
    assert pos is not None and pos.qty == Decimal("10")
    assert pos.mode is Mode.EXPERIMENTAL
    assert len(store.get_positions(acct.id)) == 1
    store.remove_position(acct.id, "AAPL")
    assert store.get_position(acct.id, "AAPL") is None


def test_transactions_and_snapshots(backend):
    store = SqliteStore(backend)
    acct = store.create_account(None, owner_user_id="u")
    txn = Transaction(
        id=new_id(), account_id=acct.id, symbol="AAPL", side="buy",
        qty=Decimal("10"), price=Decimal("150.00"),
        cash_delta=Decimal("-1500.00"), realized_pnl=None,
        created_at=utcnow(), mode=Mode.EXPERIMENTAL,
    )
    store.add_transaction(txn)
    listed = store.list_transactions(acct.id)
    assert len(listed) == 1
    assert listed[0].mode is Mode.EXPERIMENTAL

    store.add_snapshot(Snapshot(acct.id, Decimal("100000"), Decimal("98500"),
                               utcnow(), mode=Mode.EXPERIMENTAL))
    snaps = store.list_snapshots(acct.id)
    assert len(snaps) == 1 and snaps[0].mode is Mode.EXPERIMENTAL


def test_goals_plans_profiles_approvals(backend):
    store = SqliteStore(backend)
    acct = store.create_account(None, owner_user_id="u")
    goal = store.create_goal("retire rich", Decimal("1000000"), acct.id)
    assert store.get_goal(goal.id) is not None
    plan = {"summary_plain": "buy VTI", "allocations": []}
    store.save_plan(goal.id, plan)
    assert store.get_plan(goal.id) == plan

    profile = store.save_profile(
        UserProfile(account_id=acct.id, risk="high"))
    assert profile.risk == "high"
    assert store.get_profile(acct.id).risk == "high"

    req = ApprovalRequest(account_id=acct.id, trades=[], total_usd=Decimal("0"),
                          mode=Mode.EXPERIMENTAL)
    store.save_approval(req)
    assert store.get_approval(req.id) is not None
    assert store.get_approval(req.id).mode is Mode.EXPERIMENTAL
    assert store.list_approvals(acct.id) != []


def test_restart_survives(tmp_path):
    """Close the DB, reopen it: everything is still there."""
    path = tmp_path / "finkow.db"
    b1 = SqliteBackend(path)
    store = SqliteStore(b1)
    acct = store.create_account("a@b.c", owner_user_id="user-9")
    store.upsert_position(Position(acct.id, "BTC", Decimal("0.5"),
                                  Decimal("60000"), mode=Mode.EXPERIMENTAL))
    b1.close()

    b2 = SqliteBackend(path)
    store2 = SqliteStore(b2)
    loaded = store2.get_account(acct.id)
    assert loaded is not None and loaded.owner_user_id == "user-9"
    assert store2.get_position(acct.id, "BTC").qty == Decimal("0.5")
    b2.close()


def test_audit_log_durable(tmp_path):
    path = tmp_path / "finkow.db"
    b1 = SqliteBackend(path)
    log = SqliteAuditLog(b1)
    log.append(actor="executor", action="trade.executed", account_id="a1",
               details={"symbol": "AAPL"})
    b1.close()

    b2 = SqliteBackend(path)
    entries = SqliteAuditLog(b2).list(account_id="a1")
    assert len(entries) == 1
    assert entries[0].action == "trade.executed"
    assert entries[0].details == {"symbol": "AAPL"}
    assert SqliteAuditLog(b2).list(action="nope") == []
    b2.close()


def test_event_log_durable(tmp_path):
    path = tmp_path / "finkow.db"
    b1 = SqliteBackend(path)
    log = SqliteEventLog(b1)
    log.append("planner", "goal.created", {"goal_id": "g1"})
    b1.close()

    b2 = SqliteBackend(path)
    events = SqliteEventLog(b2).list(agent="planner")
    assert len(events) == 1
    assert events[0].payload == {"goal_id": "g1"}
    b2.close()


def test_credits_ledger_durable(tmp_path):
    path = tmp_path / "finkow.db"
    b1 = SqliteBackend(path)
    ledger = SqliteCreditsLedger(b1)
    ledger.credit("acct-1", 5000, tool="stripe")
    assert ledger.balance("acct-1") == 5000
    entry = ledger.credit_unique("sess-1", "acct-1", 5000, tool="stripe")
    assert entry is not None
    b1.close()

    b2 = SqliteBackend(path)
    ledger2 = SqliteCreditsLedger(b2)
    assert ledger2.balance("acct-1") == 10000
    # Idempotency survives the restart: the same session never double-credits.
    assert ledger2.credit_unique("sess-1", "acct-1", 5000, tool="stripe") is None
    assert ledger2.balance("acct-1") == 10000
    ledger2.debit("acct-1", 20, tool="aisa.market.get_quote")
    assert ledger2.balance("acct-1") == 9980
    assert ledger2.spent_since("acct-1", datetime(2000, 1, 1, tzinfo=UTC)) == 20
    b2.close()


def test_trading_cash_mutations_survive_restart(tmp_path):
    """execute_paper_* mutates account.cash: it must persist across restarts."""
    from app.trading import execute_paper_buy

    path = tmp_path / "finkow.db"
    b1 = SqliteBackend(path)
    store = SqliteStore(b1)
    acct = store.create_account(None, owner_user_id="u")
    execute_paper_buy(store, acct.id, "AAPL", Decimal("10"), Decimal("150.00"),
                      mode=Mode.EXPERIMENTAL)
    assert store.get_account(acct.id).cash == STARTING_CASH - Decimal("1500.00")
    b1.close()

    b2 = SqliteBackend(path)
    store2 = SqliteStore(b2)
    assert store2.get_account(acct.id).cash == STARTING_CASH - Decimal("1500.00")
    assert store2.get_position(acct.id, "AAPL").qty == Decimal("10")
    assert len(store2.list_transactions(acct.id)) == 1
    b2.close()


def test_concurrent_writes_do_not_corrupt(backend):
    import threading

    store = SqliteStore(backend)
    acct = store.create_account(None, owner_user_id="u")

    def write_many(n):
        for _i in range(n):
            store.add_transaction(Transaction(
                id=new_id(), account_id=acct.id, symbol="AAPL", side="buy",
                qty=Decimal("1"), price=Decimal("150.00"),
                cash_delta=Decimal("-150.00"), realized_pnl=None,
                created_at=utcnow(), mode=Mode.EXPERIMENTAL))

    threads = [threading.Thread(target=write_many, args=(25,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(store.list_transactions(acct.id)) == 100


def test_store_selector_unknown_kind_raises(monkeypatch):
    from app.main import build_storage

    monkeypatch.setenv("FINKOW_STORE", "postgres")
    with pytest.raises(RuntimeError) as exc:
        build_storage()
    assert "FINKOW_STORE" in str(exc.value)


def test_store_selector_memory_and_default(monkeypatch, tmp_path):
    from app.main import (
        DEFAULT_STORE_KIND,
        build_storage,
        resolve_store_kind,
    )
    from app.store import InMemoryStore

    # The documented default: sqlite — financial history must survive restarts.
    monkeypatch.delenv("FINKOW_STORE", raising=False)
    assert DEFAULT_STORE_KIND == "sqlite"
    assert resolve_store_kind() == "sqlite"

    monkeypatch.setenv("FINKOW_STORE", "memory")
    store, events, audit = build_storage()
    assert isinstance(store, InMemoryStore)


def test_sqlite_ledger_matches_in_memory_semantics(tmp_path):
    """The durable ledger must behave exactly like the in-memory one."""
    mem, dur = CreditsLedger(), SqliteCreditsLedger(SqliteBackend(tmp_path / "x.db"))
    for ledger in (mem, dur):
        ledger.credit("a", 100, tool="stripe")
        assert ledger.credit_unique("s1", "a", 100, tool="stripe") is not None
        assert ledger.credit_unique("s1", "a", 100, tool="stripe") is None
        ledger.debit("a", 30, tool="t")
        assert ledger.balance("a") == 170
        with pytest.raises(InsufficientCredits):
            ledger.debit("a", 1000, tool="t")
