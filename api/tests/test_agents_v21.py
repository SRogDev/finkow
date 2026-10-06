"""v2.1 agents: LearningAgent, OpportunityHunter, FinancialAnalyst,
InvestmentExecutor (+ human confirmation gate).

RED phase: pins the four agent contracts before implementation. All agents
run on the mock providers — deterministic, no network.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.agents.analyst import Analysis, FinancialAnalyst
from app.agents.events import EventLog
from app.agents.executor import InvestmentExecutor
from app.agents.hunter import OpportunityHunter
from app.agents.learning import LearningAgent
from app.agents.planner import Allocation
from app.brokerage import LiveTradingDisabledError
from app.governance.audit import AuditLog
from app.money import to_cash
from app.providers.mock import MockLLM, MockMarketData, MockWebSearch
from app.store import InMemoryStore


def _run(coro):
    return asyncio.run(coro)


def _deps():
    store = InMemoryStore()
    events = EventLog()
    audit = AuditLog()
    market = MockMarketData()
    llm = MockLLM()
    search = MockWebSearch()
    return store, events, audit, market, llm, search


# ---------------------------------------------------------------- LearningAgent


def test_learning_agent_returns_default_profile_for_new_account():
    store, events, audit, market, llm, search = _deps()
    agent = LearningAgent(llm, store, events)
    profile = agent.get_profile("acc-new")
    assert profile.risk == "medium"
    assert profile.horizon_years == 5.0


def test_learning_agent_updates_and_persists_profile():
    store, events, audit, market, llm, search = _deps()
    agent = LearningAgent(llm, store, events)
    agent.update_profile("acc1", risk="low", horizon_years=10.0)
    profile = agent.get_profile("acc1")
    assert profile.risk == "low"
    assert profile.horizon_years == 10.0


def test_learning_agent_redacts_pii_in_preferences():
    store, events, audit, market, llm, search = _deps()
    agent = LearningAgent(llm, store, events)
    agent.update_profile("acc1", preferences={"contact": "me@example.com"})
    assert agent.get_profile("acc1").preferences["contact"] == "[EMAIL_REDACTED]"


def test_learning_agent_rejects_invalid_risk():
    store, events, audit, market, llm, search = _deps()
    agent = LearningAgent(llm, store, events)
    with pytest.raises(ValueError, match="risk"):
        agent.update_profile("acc1", risk="extreme")


def test_learning_agent_plans_goal_with_profile_defaults():
    store, events, audit, market, llm, search = _deps()
    agent = LearningAgent(llm, store, events)
    agent.update_profile("acc1", risk="low", horizon_years=7.0)
    # no risk words in text -> profile risk/horizon apply
    plan = _run(agent.plan_goal("grow $2,000", account_id="acc1"))
    assert plan.risk == "low"
    assert plan.horizon_years == 7.0
    total = sum(a.weight for a in plan.allocations)
    assert abs(total - Decimal("1")) <= Decimal("0.01")


def test_learning_agent_goal_text_overrides_profile():
    store, events, audit, market, llm, search = _deps()
    agent = LearningAgent(llm, store, events)
    agent.update_profile("acc1", risk="low", horizon_years=7.0)
    plan = _run(agent.plan_goal("grow $2,000 aggressively", account_id="acc1"))
    assert plan.risk == "high"


def test_learning_agent_teaches_in_plain_language():
    store, events, audit, market, llm, search = _deps()
    agent = LearningAgent(llm, store, events)
    lesson = _run(agent.teach("diversification", "user holds only AAPL"))
    assert isinstance(lesson, str) and len(lesson) > 20
    assert "diversification" in lesson.lower()


def test_learning_agent_records_decision_history():
    store, events, audit, market, llm, search = _deps()
    agent = LearningAgent(llm, store, events)
    agent.record_decision("acc1", {"type": "invest", "symbol": "AAPL"})
    history = agent.get_profile("acc1").preferences.get("history", [])
    assert len(history) == 1
    assert history[0]["symbol"] == "AAPL"


# ---------------------------------------------------------------- OpportunityHunter


def test_hunter_scans_and_ranks_with_reasoning():
    store, events, audit, market, llm, search = _deps()
    hunter = OpportunityHunter(market, llm, events)
    opps = _run(hunter.scan(["AAPL", "NVDA", "BND"]))
    assert len(opps) >= 3
    assert all(o.reasoning for o in opps)
    scores = [o.score for o in opps]
    assert scores == sorted(scores, reverse=True)


def test_hunter_skips_unknown_symbols():
    store, events, audit, market, llm, search = _deps()
    hunter = OpportunityHunter(market, llm, events)
    opps = _run(hunter.scan(["AAPL", "NOPEXYZ"]))
    assert all(o.symbol != "NOPEXYZ" for o in opps)


def test_hunter_logs_new_agent_name():
    store, events, audit, market, llm, search = _deps()
    events = EventLog()
    hunter = OpportunityHunter(market, llm, events)
    _run(hunter.scan(["AAPL"]))
    assert [e.kind for e in events.list(agent="hunter")] == [
        "hunter.scan_started",
        "hunter.completed",
    ]


# ---------------------------------------------------------------- FinancialAnalyst


def test_analyst_reports_healthy_for_reasonable_pe():
    store, events, audit, market, llm, search = _deps()
    analyst = FinancialAnalyst(market, llm, events)
    analysis = _run(analyst.analyze("AAPL"))  # mock P/E 28.5
    assert isinstance(analysis, Analysis)
    assert analysis.symbol == "AAPL"
    assert analysis.price == Decimal("150.00")
    assert analysis.verdict == "healthy"
    assert analysis.summary_plain


def test_analyst_flags_rich_valuation():
    store, events, audit, market, llm, search = _deps()
    analyst = FinancialAnalyst(market, llm, events)
    analysis = _run(analyst.analyze("NVDA"))  # mock P/E 45.2
    assert analysis.verdict == "watch"
    assert any("valuation" in f.lower() for f in analysis.risk_flags)


def test_analyst_handles_no_earnings_multiple():
    store, events, audit, market, llm, search = _deps()
    analyst = FinancialAnalyst(market, llm, events)
    analysis = _run(analyst.analyze("BTC"))  # crypto: no P/E
    assert analysis.verdict == "neutral"
    assert analysis.pe_ratio is None


def test_analyst_rejects_unknown_symbol():
    store, events, audit, market, llm, search = _deps()
    analyst = FinancialAnalyst(market, llm, events)
    with pytest.raises(ValueError, match="unknown"):
        _run(analyst.analyze("NOPEXYZ"))


def test_analyst_never_promises_returns():
    store, events, audit, market, llm, search = _deps()
    analyst = FinancialAnalyst(market, llm, events)
    analysis = _run(analyst.analyze("AAPL"))
    lowered = analysis.summary_plain.lower()
    assert "guaranteed" not in lowered and "risk-free" not in lowered


# ---------------------------------------------------------------- InvestmentExecutor


def test_executor_invests_paper_like_pilot():
    store, events, audit, market, llm, search = _deps()
    account = store.create_account(email=None, initial_cash=Decimal("10000"))
    executor = InvestmentExecutor(store, market, events, audit)
    result = _run(
        executor.invest_paper(
            account.id,
            [Allocation("BND", Decimal("0.5"), ""), Allocation("VTI", Decimal("0.5"), "")],
        )
    )
    assert result.total_invested > 0
    positions = {p.symbol: p.qty for p in store.get_positions(account.id)}
    assert set(positions) == {"BND", "VTI"}
    # exact conservation to the cent: cash + positions == starting cash
    # (quantities carry 8dp; cash settles to cents — the v2 trading math)
    pv = sum(
        p.qty * market._prices[p.symbol] for p in store.get_positions(account.id)
    )
    assert to_cash(store.get_account(account.id).cash + pv) == Decimal("10000.00")


def test_executor_propose_does_not_move_money():
    store, events, audit, market, llm, search = _deps()
    account = store.create_account(email=None, initial_cash=Decimal("10000"))
    executor = InvestmentExecutor(store, market, events, audit)
    approval = _run(
        executor.propose(account.id, [Allocation("AAPL", Decimal("1.0"), "")])
    )
    assert approval.status == "pending"
    assert len(approval.trades) >= 1
    assert approval.total_usd > 0
    # nothing moved
    assert store.get_account(account.id).cash == Decimal("10000.00")
    assert store.get_positions(account.id) == []
    # audit recorded the request
    assert audit.list(action="approval.requested")[0].account_id == account.id


def test_executor_confirm_approved_executes_trades():
    store, events, audit, market, llm, search = _deps()
    account = store.create_account(email=None, initial_cash=Decimal("10000"))
    executor = InvestmentExecutor(store, market, events, audit)
    approval = _run(
        executor.propose(account.id, [Allocation("AAPL", Decimal("1.0"), "")])
    )
    result = _run(executor.confirm(approval.id, approved=True))
    assert result["status"] == "approved"
    assert len(result["trades"]) >= 1
    assert store.get_account(account.id).cash < Decimal("10000.00")
    assert audit.list(action="approval.granted")
    assert audit.list(action="trade.executed")


def test_executor_confirm_rejected_moves_nothing():
    store, events, audit, market, llm, search = _deps()
    account = store.create_account(email=None, initial_cash=Decimal("10000"))
    executor = InvestmentExecutor(store, market, events, audit)
    approval = _run(
        executor.propose(account.id, [Allocation("AAPL", Decimal("1.0"), "")])
    )
    result = _run(executor.confirm(approval.id, approved=False))
    assert result["status"] == "rejected"
    assert store.get_account(account.id).cash == Decimal("10000.00")
    assert audit.list(action="approval.rejected")


def test_executor_rejects_expired_approvals():
    store, events, audit, market, llm, search = _deps()
    account = store.create_account(email=None, initial_cash=Decimal("10000"))
    executor = InvestmentExecutor(
        store, market, events, audit, approval_ttl=timedelta(seconds=0)
    )
    approval = _run(
        executor.propose(account.id, [Allocation("AAPL", Decimal("1.0"), "")])
    )
    # force expiry
    req = store.get_approval(approval.id)
    req.created_at = datetime.now(UTC) - timedelta(hours=1)
    store.save_approval(req)
    result = _run(executor.confirm(approval.id, approved=True))
    assert result["status"] == "expired"
    assert store.get_account(account.id).cash == Decimal("10000.00")


def test_executor_enforces_trade_limits():
    store, events, audit, market, llm, search = _deps()
    account = store.create_account(email=None, initial_cash=Decimal("100000"))
    executor = InvestmentExecutor(
        store, market, events, audit, max_trade_usd=Decimal("100")
    )
    result = _run(
        executor.invest_paper(account.id, [Allocation("AAPL", Decimal("1.0"), "")])
    )
    assert result.trades == []  # $100k trade exceeds the $100 limit
    assert audit.list(action="trade.skipped")


def test_executor_live_path_is_disabled():
    store, events, audit, market, llm, search = _deps()
    executor = InvestmentExecutor(store, market, events, audit)
    with pytest.raises(LiveTradingDisabledError):
        executor.submit_live_order("AAPL", Decimal("1"))


def test_executor_unknown_approval_raises():
    store, events, audit, market, llm, search = _deps()
    executor = InvestmentExecutor(store, market, events, audit)
    with pytest.raises(ValueError, match="approval not found"):
        _run(executor.confirm("nope", approved=True))
