"""Agent pipeline: GoalPlanner, OpportunityRadar, PortfolioPilot, Explainer.

RED phase: pins the agent contracts before implementation. All agents run on
the mock providers — deterministic, no network.
"""

import asyncio
import json
from decimal import Decimal

import pytest

from app.agents.events import EventLog
from app.providers.mock import MockLLM, MockMarketData, MockWebSearch
from app.store import InMemoryStore


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- events


def test_event_log_is_append_only_and_ordered():
    log = EventLog()
    log.append("planner", "goal.created", {"text": "grow money"})
    log.append("radar", "radar.completed", {"count": 3})
    log.append("planner", "plan.generated", {"symbols": ["AAPL"]})
    events = log.list()
    assert [e.kind for e in events] == ["goal.created", "radar.completed", "plan.generated"]
    assert [e.agent for e in events] == ["planner", "radar", "planner"]
    assert all(e.id and e.created_at for e in events)
    # filtering keeps global order
    assert [e.kind for e in log.list(agent="planner")] == ["goal.created", "plan.generated"]
    assert len(log.list(limit=2)) == 2
    # no mutation API: the list is a snapshot
    events.clear()
    assert len(log.list()) == 3


# ---------------------------------------------------------------- planner


def test_parse_goal_extracts_amount_horizon_risk():
    from app.agents.planner import parse_goal

    spec = parse_goal("grow $1,000 over 5 years, low risk")
    assert spec.amount == Decimal("1000")
    assert spec.horizon_years == 5
    assert spec.risk == "low"

    aggressive = parse_goal("aggressive growth with 10000 over 10 years")
    assert aggressive.risk == "high"
    assert aggressive.amount == Decimal("1000")  # no $ sign -> default
    assert aggressive.horizon_years == 10

    default = parse_goal("make my money grow")
    assert default.risk == "medium" and default.horizon_years == 5


def test_planner_produces_valid_plain_language_plan():
    from app.agents.planner import GoalPlanner

    log = EventLog()
    planner = GoalPlanner(MockLLM(), events=log)
    plan = _run(planner.plan("grow $1,000 over 5 years, low risk"))
    weights = [a.weight for a in plan.allocations]
    assert abs(sum(weights) - Decimal("1")) < Decimal("0.001")
    assert len(plan.allocations) >= 2
    assert all(a.symbol and a.rationale for a in plan.allocations)
    assert plan.risk == "low"
    # plain language, no trading-desk jargon
    lowered = plan.summary_plain.lower()
    for jargon in ("candlestick", "derivative", "leverage", "short squeeze"):
        assert jargon not in lowered
    assert "1000" in plan.summary_plain
    assert log.list(agent="planner")


def test_planner_rejects_incoherent_llm_output():
    from app.agents.planner import GoalPlanner

    class BadLLM:
        name = "bad"

        async def complete(self, messages, *, system="", json_mode=False):
            return json.dumps({"allocations": [{"symbol": "X", "weight": 0.5}]})

    with pytest.raises(ValueError):
        _run(GoalPlanner(BadLLM()).plan("grow money"))


# ---------------------------------------------------------------- radar


def test_radar_returns_ranked_opportunities_with_reasoning():
    from app.agents.radar import OpportunityRadar

    log = EventLog()
    radar = OpportunityRadar(MockMarketData(), MockLLM(), events=log)
    opps = _run(radar.scan(["AAPL", "NVDA", "BND"]))
    assert len(opps) >= 3
    scores = [o.score for o in opps]
    assert scores == sorted(scores, reverse=True)
    for o in opps:
        assert o.symbol and o.reasoning and o.price > 0
    blob = " ".join(o.reasoning for o in opps)
    assert "150.00" in blob  # real mock price cited, not invented
    assert "radar.completed" in [e.kind for e in log.list(agent="radar")]


def test_radar_skips_unknown_symbols():
    from app.agents.radar import OpportunityRadar

    radar = OpportunityRadar(MockMarketData(), MockLLM())
    opps = _run(radar.scan(["AAPL", "NOPEXYZ", "BND"]))
    assert {o.symbol for o in opps} == {"AAPL", "BND"}


# ---------------------------------------------------------------- pilot


def test_pilot_invests_paper_money_by_weight():
    from app.agents.pilot import PortfolioPilot
    from app.agents.planner import Allocation

    store = InMemoryStore()
    account = store.create_account(email=None)
    log = EventLog()
    pilot = PortfolioPilot(store, MockMarketData(), events=log)

    result = _run(
        pilot.invest(
            account.id,
            [Allocation("AAPL", Decimal("0.5"), ""), Allocation("BND", Decimal("0.5"), "")],
        )
    )
    assert result.account_id == account.id
    assert len(result.trades) == 2
    assert all(t.side == "buy" for t in result.trades)
    # $100k split evenly at mock prices -> total still $100k (paper)
    positions = {p.symbol: p for p in store.get_positions(account.id)}
    assert positions["AAPL"].qty > 0 and positions["BND"].qty > 0
    kinds = [e.kind for e in log.list(agent="pilot")]
    assert "pilot.invest_started" in kinds and "pilot.invest_completed" in kinds


def test_pilot_rebalances_toward_targets():
    from app.agents.pilot import PortfolioPilot
    from app.agents.planner import Allocation

    store = InMemoryStore()
    account = store.create_account(email=None)
    pilot = PortfolioPilot(store, MockMarketData())
    _run(pilot.invest(account.id, [Allocation("AAPL", Decimal("1.0"), "")]))
    # now rebalance to 50/50: should sell some AAPL and buy BND
    result = _run(
        pilot.invest(
            account.id,
            [Allocation("AAPL", Decimal("0.5"), ""), Allocation("BND", Decimal("0.5"), "")],
        )
    )
    sides = {t.side for t in result.trades}
    assert "sell" in sides and "buy" in sides


def test_pilot_rejects_unknown_account():
    from app.agents.pilot import PortfolioPilot
    from app.agents.planner import Allocation

    with pytest.raises(ValueError, match="account not found"):
        _run(
            PortfolioPilot(InMemoryStore(), MockMarketData()).invest(
                "nope", [Allocation("AAPL", Decimal("1.0"), "")]
            )
        )


# ---------------------------------------------------------------- explainer


def test_explainer_answers_why_portfolio_moved():
    from app.agents.explainer import Explainer

    store = InMemoryStore()
    account = store.create_account(email=None)
    market = MockMarketData()
    # buy 0.5 BTC @ 60000 (paper), then market moves to 66000
    from app.trading import execute_paper_buy

    execute_paper_buy(store, account.id, "BTC", Decimal("0.5"), Decimal("60000.00"))
    market.set_price("BTC", Decimal("66000.00"))

    log = EventLog()
    explainer = Explainer(store, market, MockLLM(), MockWebSearch(), events=log)
    out = _run(explainer.explain(account.id, "why did my portfolio move today?"))
    assert out["grounded"] is True
    assert "103000" in out["answer"].replace(",", "")  # real computed total
    assert "BTC" in out["answer"]
    assert [e.kind for e in log.list(agent="explainer")] == ["explainer.answered"]
