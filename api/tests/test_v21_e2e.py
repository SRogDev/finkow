"""v2.1 end-to-end: the full SIMULATED investment flow, exact balances.

RED phase: the acceptance walkthrough from the brief — fund -> goal -> plan ->
hunt -> analyze -> propose -> confirm -> execute -> portfolio -> explain ->
audit. Every balance asserted exactly. No real money anywhere: all providers
are mocks, the brokerage is a mock, Stripe is unconfigured, and the live
trading path raises.

Mock prices (deterministic): BND 75.00, VTI 280.00, AAPL 150.00, MSFT 420.00.
Low-risk plan: BND 0.50 / VTI 0.30 / AAPL 0.10 / MSFT 0.10 of $10,000.
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


def test_full_simulated_investment_flow(client):
    c = client

    # 1. fund the paper account with exactly $10,000
    created = c.post(
        "/api/goals",
        json={"text": "grow $10,000 low risk for 5 years", "amount": "10000"},
    )
    assert created.status_code == 200
    goal_id = created.json()["goal_id"]
    account_id = created.json()["account_id"]
    portfolio = c.get(f"/api/goals/{goal_id}/portfolio").json()
    assert portfolio["cash"] == "10000.00"
    assert portfolio["total_value"] == "10000.00"
    assert portfolio["positions"] == []

    # 2. plan: low-risk allocation, weights sum to exactly 1
    plan = c.get(f"/api/goals/{goal_id}/plan").json()
    assert plan["risk_level"] == "low"
    weights = {a["symbol"]: Decimal(a["weight"]) for a in plan["allocations"]}
    assert weights == {
        "BND": Decimal("0.5000"),
        "VTI": Decimal("0.3000"),
        "AAPL": Decimal("0.1000"),
        "MSFT": Decimal("0.1000"),
    }
    assert sum(weights.values()) == Decimal("1.0000")

    # 3. hunt: ranked opportunities with reasoning
    opps = c.get(f"/api/radar/opportunities?goal_id={goal_id}").json()["opportunities"]
    assert len(opps) >= 3
    assert all(o["reasoning"] for o in opps)

    # 4. analyze: fundamentals verdict for a holding
    analysis = c.get("/api/analyze/AAPL").json()
    assert analysis["symbol"] == "AAPL"
    assert analysis["verdict"] == "healthy"
    assert analysis["summary_plain"]

    # 5. orchestrator invest: PROPOSES, does not execute (the money gate)
    run = c.post(
        "/api/harness/run",
        json={"text": "invest $10,000 low risk for 5 years", "account_id": account_id},
    ).json()
    assert run["intent"] == "invest"
    assert run["requires_human"] is True
    assert "approv" in run["human_question"].lower()
    approval_id = run["results"]["approval_id"]
    proposed = run["results"]["proposed_trades"]
    assert len(proposed) == 4
    # money has NOT moved
    assert c.get(f"/api/goals/{goal_id}/portfolio").json()["cash"] == "10000.00"

    # 6. human confirms -> paper execution
    confirmed = c.post(
        "/api/executor/confirm", json={"approval_id": approval_id, "approved": True}
    ).json()
    assert confirmed["status"] == "approved"
    assert len(confirmed["trades"]) == 4

    # 7. portfolio: exact conservation — $10,000 in, $10,000 total out
    portfolio = c.get(f"/api/goals/{goal_id}/portfolio").json()
    assert portfolio["cash"] == "0.00"
    assert portfolio["total_value"] == "10000.00"
    by_symbol = {p["symbol"]: p for p in portfolio["positions"]}
    assert set(by_symbol) == {"BND", "VTI", "AAPL", "MSFT"}
    assert by_symbol["BND"]["market_value"] == "5000.00"
    assert by_symbol["VTI"]["market_value"] == "3000.00"
    assert by_symbol["AAPL"]["market_value"] == "1000.00"
    assert by_symbol["MSFT"]["market_value"] == "1000.00"
    # allocation adds up
    alloc = sum(Decimal(v) for v in portfolio["allocation"].values())
    assert abs(alloc - Decimal("1")) < Decimal("0.001")

    # 8. explain: grounded answer about the portfolio
    explained = c.post(
        "/api/explain",
        json={"account_id": account_id, "question": "why did my portfolio move today?"},
    ).json()
    assert explained["grounded"] is True
    assert explained["answer"]

    # 9. audit: the money trail exists
    entries = c.get(f"/api/audit?account_id={account_id}").json()["entries"]
    actions = [e["action"] for e in entries]
    assert "approval.requested" in actions
    assert "approval.granted" in actions
    assert actions.count("trade.executed") == 4
    assert all(e["outcome"] == "success" for e in entries if e["action"] == "trade.executed")

    # 10. agent activity: the orchestrator narrated the run
    activity = c.get("/api/agents/activity").json()["events"]
    kinds = [e["kind"] for e in activity]
    assert "orchestrator.run_started" in kinds
    assert "orchestrator.run_completed" in kinds


def test_e2e_rejected_approval_moves_nothing(client):
    c = client
    created = c.post(
        "/api/goals",
        json={"text": "grow $10,000 low risk for 5 years", "amount": "10000"},
    ).json()
    goal_id, account_id = created["goal_id"], created["account_id"]
    run = c.post(
        "/api/harness/run",
        json={"text": "invest $10,000 low risk for 5 years", "account_id": account_id},
    ).json()
    rejected = c.post(
        "/api/executor/confirm",
        json={"approval_id": run["results"]["approval_id"], "approved": False},
    ).json()
    assert rejected["status"] == "rejected"
    portfolio = c.get(f"/api/goals/{goal_id}/portfolio").json()
    assert portfolio["cash"] == "10000.00"
    assert portfolio["total_value"] == "10000.00"
    assert portfolio["positions"] == []
