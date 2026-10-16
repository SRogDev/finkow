"""v2.1 routes: harness, executor gate, audit, billing, brokerage, profiles.

RED phase: pins the v2.1 HTTP contract before implementation.
"""

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


def _account(client, cash="10000"):
    # /api/accounts always funds the $100k default; fund exact cash via goals.
    r = client.post("/api/goals", json={"text": "test funding", "amount": cash})
    assert r.status_code == 200
    return r.json()["account_id"]


# ---------------------------------------------------------------- harness


def test_harness_run_opportunities(client):
    r = client.post("/api/harness/run", json={"text": "find me opportunities"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "opportunities"
    assert len(body["results"]["opportunities"]) >= 3
    assert body["requires_human"] is False
    assert len(body["checkpoints"]) == 7


def test_harness_run_unclear_asks_for_clarification(client):
    r = client.post("/api/harness/run", json={"text": "blorpt fnord xyzzy"})
    assert r.status_code == 200
    body = r.json()
    assert body["requires_human"] is True
    assert body["human_question"]


def test_harness_invest_proposes_and_confirms(client):
    account_id = _account(client)
    r = client.post(
        "/api/harness/run",
        json={"text": "invest $10,000 low risk for 5 years", "account_id": account_id},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "invest"
    assert body["requires_human"] is True
    approval_id = body["results"]["approval_id"]
    # money hasn't moved
    assert client.get(f"/api/accounts/{account_id}/portfolio").json()["cash"] == "10000.00"
    # confirm via the gate
    c = client.post(
        "/api/executor/confirm", json={"approval_id": approval_id, "approved": True}
    )
    assert c.status_code == 200
    assert c.json()["status"] == "approved"
    assert len(c.json()["trades"]) >= 1
    portfolio = client.get(f"/api/accounts/{account_id}/portfolio").json()
    assert portfolio["total_value"] == "10000.00"


def test_harness_run_requires_text(client):
    assert client.post("/api/harness/run", json={"text": "  "}).status_code == 400


# ---------------------------------------------------------------- executor gate


def test_executor_propose_then_reject(client):
    account_id = _account(client)
    p = client.post(
        "/api/executor/propose",
        json={
            "account_id": account_id,
            "allocations": [{"symbol": "AAPL", "weight": "1.0"}],
        },
    )
    assert p.status_code == 200
    approval_id = p.json()["approval_id"]
    assert p.json()["status"] == "pending"
    c = client.post(
        "/api/executor/confirm", json={"approval_id": approval_id, "approved": False}
    )
    assert c.json()["status"] == "rejected"
    assert client.get(f"/api/accounts/{account_id}/portfolio").json()["cash"] == "10000.00"


def test_executor_confirm_unknown_approval_404(client):
    r = client.post(
        "/api/executor/confirm", json={"approval_id": "nope", "approved": True}
    )
    assert r.status_code == 404


# ---------------------------------------------------------------- audit


def test_audit_log_lists_money_actions(client):
    account_id = _account(client)
    p = client.post(
        "/api/executor/propose",
        json={
            "account_id": account_id,
            "allocations": [{"symbol": "AAPL", "weight": "1.0"}],
        },
    )
    approval_id = p.json()["approval_id"]
    client.post(
        "/api/executor/confirm", json={"approval_id": approval_id, "approved": True}
    )
    r = client.get(f"/api/audit?account_id={account_id}")
    assert r.status_code == 200
    actions = [e["action"] for e in r.json()["entries"]]
    assert "approval.requested" in actions
    assert "approval.granted" in actions
    assert "trade.executed" in actions


# ---------------------------------------------------------------- billing


def test_billing_checkout_503_without_key(client, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    r = client.post(
        "/api/billing/checkout",
        json={
            "price_id": "price_123",
            "success_url": "https://x.test/ok",
            "cancel_url": "https://x.test/no",
        },
    )
    assert r.status_code == 503


def test_billing_webhook_503_without_key(client, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    r = client.post("/api/billing/webhook", content=b"{}")
    assert r.status_code == 503


# ---------------------------------------------------------------- brokerage


def test_brokerage_account_and_order_flow(client):
    r = client.get("/api/brokerage/account")
    assert r.status_code == 200
    assert r.json()["live"] is False
    o = client.post(
        "/api/brokerage/orders",
        json={"symbol": "AAPL", "qty": "2", "side": "buy"},
    )
    assert o.status_code == 200
    order = o.json()
    assert order["status"] == "filled"
    fetched = client.get(f"/api/brokerage/orders/{order['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == order["id"]


def test_brokerage_rejects_bad_side(client):
    r = client.post(
        "/api/brokerage/orders", json={"symbol": "AAPL", "qty": "2", "side": "hold"}
    )
    assert r.status_code == 400


# ---------------------------------------------------------------- profiles + PII


def test_profile_roundtrip(client):
    account_id = _account(client)
    r = client.put(
        f"/api/profile/{account_id}",
        json={"risk": "low", "horizon_years": 10.0, "preferences": {"style": "calm"}},
    )
    assert r.status_code == 200
    assert r.json()["risk"] == "low"
    g = client.get(f"/api/profile/{account_id}")
    assert g.json()["horizon_years"] == 10.0


def test_profile_rejects_bad_risk(client):
    account_id = _account(client)
    r = client.put(f"/api/profile/{account_id}", json={"risk": "extreme"})
    assert r.status_code == 400


def test_goal_text_pii_is_redacted_before_storage(client):
    r = client.post(
        "/api/goals", json={"text": "grow $1,000, contact me at me@example.com"}
    )
    assert r.status_code == 200
    goal = client.get(f"/api/goals/{r.json()['goal_id']}").json()
    assert "me@example.com" not in goal["text"]
    assert "[EMAIL_REDACTED]" in goal["text"]
