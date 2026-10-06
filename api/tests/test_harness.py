"""Orchestrator harness: single entry, confidence routing, checkpoints.

RED phase: pins the harness contracts before implementation. Adapted from
Polygrow's ai_mind (entry -> context -> intent_router -> delegate -> verify ->
synthesize -> memory_write), as plain-Python stages — no LangGraph needed at
this scale. Confidence threshold 0.6, same as Polygrow's router.
"""

import asyncio
from decimal import Decimal

from app.agents.events import EventLog
from app.governance.audit import AuditLog
from app.harness.orchestrator import Orchestrator, RunRequest, RunResult
from app.harness.router import CONFIDENCE_THRESHOLD, classify_intent, route
from app.harness.state import RunState
from app.providers.mock import MockLLM, MockMarketData, MockWebSearch
from app.store import InMemoryStore


def _run(coro):
    return asyncio.run(coro)


def _harness():
    store = InMemoryStore()
    events = EventLog()
    return (
        Orchestrator(
            store=store,
            market=MockMarketData(),
            llm=MockLLM(),
            search=MockWebSearch(),
            events=events,
            audit=AuditLog(),
        ),
        store,
        events,
    )


# ---------------------------------------------------------------- router


def test_confidence_threshold_matches_polygrow():
    assert CONFIDENCE_THRESHOLD == 0.6


def test_router_classifies_invest_intent():
    intent, confidence = classify_intent("I want to invest $5,000 for retirement")
    assert intent == "invest"
    assert confidence >= CONFIDENCE_THRESHOLD


def test_router_classifies_opportunities_intent():
    intent, confidence = classify_intent("find me good opportunities this week")
    assert intent == "opportunities"
    assert confidence >= CONFIDENCE_THRESHOLD


def test_router_classifies_analyze_intent():
    intent, confidence = classify_intent("analyze AAPL fundamentals and valuation")
    assert intent == "analyze"


def test_router_classifies_explain_intent():
    intent, confidence = classify_intent("why did my portfolio move today?")
    assert intent == "explain"


def test_router_classifies_learn_intent():
    intent, confidence = classify_intent("teach me what diversification means")
    assert intent == "learn"


def test_router_low_confidence_routes_to_clarify():
    intent, confidence = classify_intent("blorpt fnord xyzzy")
    assert confidence < CONFIDENCE_THRESHOLD
    state = RunState(intent=intent, confidence=confidence, text="blorpt")
    assert route(state) == "clarify"


def test_router_confident_routes_to_delegate():
    state = RunState(intent="invest", confidence=0.9, text="invest $1000")
    assert route(state) == "delegate"


# ---------------------------------------------------------------- orchestrator


def test_orchestrator_runs_opportunities_end_to_end():
    orch, store, events = _harness()
    result = _run(orch.run(RunRequest(text="find me opportunities")))
    assert isinstance(result, RunResult)
    assert result.intent == "opportunities"
    assert result.error is None
    assert len(result.results["opportunities"]) >= 3
    # checkpoints recorded per stage
    assert [c["stage"] for c in result.checkpoints] == [
        "entry",
        "context_gather",
        "intent_classify",
        "delegate",
        "verify",
        "synthesize",
        "memory_write",
    ]
    assert events.list(agent="orchestrator")


def test_orchestrator_asks_for_clarification_when_unsure():
    orch, store, events = _harness()
    result = _run(orch.run(RunRequest(text="blorpt fnord xyzzy")))
    assert result.requires_human is True
    assert result.human_question  # asks what the user meant
    assert result.results == {}


def test_orchestrator_invest_returns_proposal_not_execution():
    """The money gate: invest intents propose; they never auto-execute."""
    orch, store, events = _harness()
    account = store.create_account(email=None, initial_cash=Decimal("10000"))
    result = _run(
        orch.run(
            RunRequest(text="invest $10,000 low risk for 5 years", account_id=account.id)
        )
    )
    assert result.intent == "invest"
    assert result.requires_human is True
    assert "approv" in result.human_question.lower()
    approval_id = result.results["approval_id"]
    # nothing moved until confirmation
    assert store.get_account(account.id).cash == Decimal("10000.00")
    assert store.get_approval(approval_id).status == "pending"


def test_orchestrator_handles_agent_failure_gracefully():
    orch, store, events = _harness()

    class BoomMarket(MockMarketData):
        async def get_quote(self, symbol):
            raise RuntimeError("boom")

    orch2 = Orchestrator(
        store=store,
        market=BoomMarket(),
        llm=MockLLM(),
        search=MockWebSearch(),
        events=events,
        audit=AuditLog(),
    )
    result = _run(orch2.run(RunRequest(text="find me opportunities")))
    assert result.error is not None
    assert "boom" in result.error
    # the failure is recorded, not raised
    assert any(e.kind == "orchestrator.stage_failed" for e in events.list())


def test_orchestrator_explain_uses_account():
    orch, store, events = _harness()
    account = store.create_account(email=None, initial_cash=Decimal("5000"))
    result = _run(
        orch.run(
            RunRequest(text="why did my portfolio move?", account_id=account.id)
        )
    )
    assert result.intent == "explain"
    assert result.results["answer"]


def test_orchestrator_verifies_specialist_output():
    orch, store, events = _harness()
    result = _run(orch.run(RunRequest(text="find me opportunities")))
    assert result.results["verified"] is True
