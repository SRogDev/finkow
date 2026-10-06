"""v2 API: goal -> plan -> radar -> paper invest -> portfolio -> explain.

RED phase: full walkthrough against the mock providers. v1 endpoints are
covered by the untouched v1 suite; this file pins the v2 contract.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import main
from app.providers.mock import MockLLM, MockMarketData, MockWebSearch


@pytest.fixture()
def client():
    main.reset_state()
    main.app.dependency_overrides[main.get_market_port] = lambda: MockMarketData()
    main.app.dependency_overrides[main.get_llm] = lambda: MockLLM()
    main.app.dependency_overrides[main.get_search] = lambda: MockWebSearch()
    main.app.dependency_overrides[main.get_market] = lambda: MockMarketData()
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_goal_to_plan_flow(client):
    c = client
    created = c.post("/api/goals", json={"text": "grow $1,000 over 5 years, low risk"})
    assert created.status_code == 200
    body = created.json()
    goal_id, account_id = body["goal_id"], body["account_id"]
    assert body["amount"] == "1000.00"

    goal = c.get(f"/api/goals/{goal_id}").json()
    assert goal["account_id"] == account_id
    assert goal["amount"] == "1000.00"

    plan = c.get(f"/api/goals/{goal_id}/plan").json()
    assert plan["risk_level"] == "low"
    weights = [Decimal(a["weight"]) for a in plan["allocations"]]
    assert abs(sum(weights) - Decimal("1")) < Decimal("0.001")
    assert plan["summary_plain"]
    # second fetch returns the stored plan, identical
    assert c.get(f"/api/goals/{goal_id}/plan").json() == plan


def test_goal_plan_404_for_unknown_goal(client):
    assert client.get("/api/goals/nope/plan").status_code == 404


def test_radar_returns_opportunities(client):
    c = client
    resp = c.get("/api/radar/opportunities?symbols=AAPL,NVDA,BND")
    assert resp.status_code == 200
    opps = resp.json()["opportunities"]
    assert len(opps) >= 3
    assert all(o["reasoning"] and o["score"] is not None for o in opps)


def test_full_invest_walkthrough(client):
    c = client
    created = c.post("/api/goals", json={"text": "grow $1,000 over 5 years, low risk"}).json()
    account_id = created["account_id"]
    gid = created["goal_id"]

    plan = c.get(f"/api/goals/{gid}/plan").json()
    radar = c.get(f"/api/radar/opportunities?goal_id={gid}").json()
    assert len(radar["opportunities"]) >= 3
    invest = c.post(
        "/api/portfolio/invest",
        json={
            "account_id": account_id,
            "allocations": [
                {"symbol": a["symbol"], "weight": a["weight"]} for a in plan["allocations"]
            ],
        },
    )
    assert invest.status_code == 200
    assert len(invest.json()["trades"]) >= 2

    pf = c.get(f"/api/goals/{gid}/portfolio").json()
    assert pf["account_id"] == account_id
    assert pf["total_value"] == "1000.00"  # mock prices static: paper value conserved
    assert len(pf["positions"]) >= 2

    explained = c.post(
        "/api/explain",
        json={"account_id": account_id, "question": "why did my portfolio move today?"},
    ).json()
    assert explained["grounded"] is True
    assert "1000" in explained["answer"].replace(",", "")

    activity = c.get("/api/agents/activity").json()["events"]
    kinds = [e["kind"] for e in activity]
    for expected in (
        "goal.created",
        "plan.generated",
        "radar.completed",
        "pilot.invest_completed",
        "explainer.answered",
    ):
        assert expected in kinds, kinds
    # append-only order preserved
    assert kinds.index("goal.created") < kinds.index("plan.generated")


def test_invest_rejects_bad_weights(client):
    c = client
    account_id = c.post("/api/goals", json={"text": "grow money"}).json()["account_id"]
    resp = c.post(
        "/api/portfolio/invest",
        json={"account_id": account_id, "allocations": [{"symbol": "AAPL", "weight": "-0.5"}]},
    )
    assert resp.status_code == 400


def test_v1_endpoints_still_work_alongside_v2(client):
    # v1 behavior unchanged (v1 market overridden with the mock port here;
    # the dedicated v1 suite covers the real provider chain).
    c = client
    account_id = c.post("/api/accounts", json={}).json()["account_id"]
    q = c.get("/api/quotes/AAPL").json()
    assert Decimal(q["price"]) == Decimal("150.00")
    buy = c.post(
        "/api/orders",
        json={"account_id": account_id, "symbol": "AAPL", "side": "buy", "quantity": "10"},
    ).json()
    assert buy["cash_after"] == "98500.00"
    pf = c.get(f"/api/accounts/{account_id}/portfolio").json()
    assert pf["total_value"] == "100000.00"
