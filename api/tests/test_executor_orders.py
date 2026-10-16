
"""Executor <-> order-lifecycle wiring: propose creates draft orders, confirm
drives them through the lifecycle, and the per-user daily trade limit holds
across a user's accounts."""

import asyncio
from decimal import Decimal

from app.agents.events import EventLog
from app.agents.executor import InvestmentExecutor
from app.agents.planner import Allocation
from app.governance.audit import AuditLog
from app.orders import OrderLifecycle, OrderStatus
from app.providers.mock import MockMarketData
from app.store import InMemoryStore


def _run(coro):
    return asyncio.run(coro)


def _executor(store: InMemoryStore, **kwargs) -> InvestmentExecutor:
    return InvestmentExecutor(
        store, MockMarketData(), EventLog(), AuditLog(), **kwargs
    )


def test_propose_creates_draft_orders_linked_to_approval():
    store = InMemoryStore()
    account = store.create_account(
        email=None, initial_cash=Decimal("100000"), owner_user_id="u1"
    )
    executor = _executor(store)
    approval = _run(executor.propose(account.id, [Allocation("AAPL", Decimal("1.0"), "")]))
    orders = OrderLifecycle(store).list_for_approval(account.id, approval.id)
    assert len(orders) >= 1
    assert all(o.status == OrderStatus.DRAFT for o in orders)
    assert all(o.approval_id == approval.id for o in orders)
    assert all(o.simulated is True for o in orders)
    # nothing moved: the proposal is only a plan
    assert store.get_account(account.id).cash == Decimal("100000")


def test_confirm_approved_drives_orders_to_filled():
    store = InMemoryStore()
    account = store.create_account(
        email=None, initial_cash=Decimal("100000"), owner_user_id="u1"
    )
    executor = _executor(store)
    approval = _run(executor.propose(account.id, [Allocation("AAPL", Decimal("0.1"), "")]))
    result = _run(executor.confirm(approval.id, approved=True))
    assert result["status"] == "approved"
    orders = OrderLifecycle(store).list_for_approval(account.id, approval.id)
    assert orders, "expected order records"
    assert all(o.status == OrderStatus.FILLED for o in orders)
    assert all(o.provider_order_id is None for o in orders)  # mock: no provider
    # every fill links back to its order
    txns = store.list_transactions(account.id)
    assert txns and all(t.order_id for t in txns)
    assert {t.order_id for t in txns} == {o.id for o in orders}


def test_confirm_rejected_cancels_draft_orders():
    store = InMemoryStore()
    account = store.create_account(email=None, initial_cash=Decimal("100000"))
    executor = _executor(store)
    approval = _run(executor.propose(account.id, [Allocation("AAPL", Decimal("1.0"), "")]))
    result = _run(executor.confirm(approval.id, approved=False))
    assert result["status"] == "rejected"
    orders = OrderLifecycle(store).list_for_approval(account.id, approval.id)
    assert orders
    assert all(o.status == OrderStatus.CANCELLED for o in orders)
    assert store.get_account(account.id).cash == Decimal("100000")


def test_invest_paper_direct_path_records_orders():
    store = InMemoryStore()
    account = store.create_account(email=None, initial_cash=Decimal("100000"))
    executor = _executor(store)
    result = _run(executor.invest_paper(account.id, [Allocation("AAPL", Decimal("0.1"), "")]))
    assert result.trades, "expected trades"
    orders = store.list_orders(account.id)
    assert orders
    assert all(o.status == OrderStatus.FILLED for o in orders)
    assert all(o.approval_id is None for o in orders)  # direct path, no approval
    assert all(o.simulated is True for o in orders)


def test_per_user_daily_trade_limit_spans_accounts():
    store = InMemoryStore()
    a1 = store.create_account(
        email=None, initial_cash=Decimal("100000"), owner_user_id="u9"
    )
    a2 = store.create_account(
        email=None, initial_cash=Decimal("100000"), owner_user_id="u9"
    )
    executor = _executor(store, max_daily_trades_per_user=1)
    r1 = _run(executor.invest_paper(a1.id, [Allocation("AAPL", Decimal("0.1"), "")]))
    assert r1.trades, "first trade should execute"
    # the user already traded once today: the second account is blocked
    r2 = _run(executor.invest_paper(a2.id, [Allocation("AAPL", Decimal("0.1"), "")]))
    assert r2.trades == []
    skipped = [e for e in executor._audit.list(action="trade.skipped")]
    assert skipped
    assert any("user" in (e.details.get("reason") or "") for e in skipped)
    # the blocked trade is recorded as a rejected order, not dropped
    rejected = store.list_orders(a2.id, status=OrderStatus.REJECTED)
    assert len(rejected) == 1


def test_risk_breach_in_executor_records_rejected_order():
    store = InMemoryStore()
    account = store.create_account(email=None, initial_cash=Decimal("100000"))
    executor = _executor(store, max_trade_usd=Decimal("100"))
    result = _run(
        executor.invest_paper(account.id, [Allocation("AAPL", Decimal("1.0"), "")])
    )
    assert result.trades == []
    rejected = store.list_orders(account.id, status=OrderStatus.REJECTED)
    assert len(rejected) == 1
    assert "max_trade_usd" in (rejected[0].reject_reason or "")
