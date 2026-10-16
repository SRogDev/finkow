"""Account ownership: every account-scoped endpoint enforces it.

- Auth enabled: user B touching user A's account -> 403; unknown -> 404.
- Dev mode (no secret): the single-user path keeps working with no headers.
"""

import base64
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import main
from app.store import Account

TEST_SECRET = "test-ownership-jwt-secret-0123456789abcdef"


def forge(payload: dict, secret: str = TEST_SECRET) -> str:
    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = b64(json.dumps(payload).encode())
    sig = b64(hmac.new(secret.encode(), f"{header}.{body}".encode(),
                       hashlib.sha256).digest())
    return f"{header}.{body}.{sig}"


def token_for(user_id: str, secret: str = TEST_SECRET) -> str:
    return forge({"sub": user_id, "exp": int(time.time()) + 3600}, secret)


def auth_headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer {token_for(user_id)}"}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_SECRET)
    main.reset_state()
    c = TestClient(main.app)
    yield c
    main.app.dependency_overrides.clear()
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    main.reset_state()


def create_account(c: TestClient, user: str) -> str:
    resp = c.post("/api/accounts", json={}, headers=auth_headers(user))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["owner_user_id"] == user
    return body["account_id"]


def test_auth_required_when_enabled(client):
    resp = client.post("/api/accounts", json={})
    assert resp.status_code == 401


def test_wrong_signature_is_401(client):
    bad = forge({"sub": "alice", "exp": int(time.time()) + 3600},
                secret="wrong")
    resp = client.post("/api/accounts", json={},
                       headers={"Authorization": f"Bearer {bad}"})
    assert resp.status_code == 401


def test_owner_can_use_account(client):
    acct = create_account(client, "alice")
    resp = client.get(f"/api/accounts/{acct}/portfolio",
                      headers=auth_headers("alice"))
    assert resp.status_code == 200
    assert resp.json()["mode"] == "experimental"
    assert resp.json()["virtual"] is True


def test_other_user_gets_403(client):
    acct = create_account(client, "alice")
    for method, url, kwargs in [
        ("get", f"/api/accounts/{acct}/portfolio", {}),
        ("get", f"/api/accounts/{acct}/transactions", {}),
        ("get", f"/api/accounts/{acct}/history", {}),
        ("post", "/api/orders", {"json": {"account_id": acct, "symbol": "AAPL",
                                          "side": "buy", "quantity": "1"}}),
        ("post", "/api/executor/propose", {"json": {"account_id": acct,
                                                    "allocations": []}}),
    ]:
        resp = client.request(method, url, headers=auth_headers("mallory"),
                              **kwargs)
        assert resp.status_code == 403, (method, url, resp.text)


def test_unknown_account_is_404_not_403(client):
    resp = client.get("/api/accounts/does-not-exist/portfolio",
                      headers=auth_headers("alice"))
    assert resp.status_code == 404


def test_goal_endpoints_enforce_ownership(client):
    resp = client.post("/api/goals", json={"text": "save $1000",
                                           "amount": "1000.00"},
                       headers=auth_headers("alice"))
    assert resp.status_code == 200
    goal_id = resp.json()["goal_id"]
    _acct = resp.json()["account_id"]  # owned by alice; mallory must be rejected

    resp = client.get(f"/api/goals/{goal_id}", headers=auth_headers("mallory"))
    assert resp.status_code == 403
    resp = client.get(f"/api/goals/{goal_id}", headers=auth_headers("alice"))
    assert resp.status_code == 200
    resp = client.get(f"/api/goals/{goal_id}/portfolio",
                      headers=auth_headers("mallory"))
    assert resp.status_code == 403


def test_credits_balance_enforces_ownership(client):
    acct = create_account(client, "alice")
    resp = client.get("/api/billing/credits/balance",
                      params={"account_id": acct},
                      headers=auth_headers("mallory"))
    assert resp.status_code == 403
    resp = client.get("/api/billing/credits/balance",
                      params={"account_id": acct},
                      headers=auth_headers("alice"))
    assert resp.status_code == 200


def test_dev_mode_single_user_path_needs_no_headers(monkeypatch):
    """Secret unset -> auth disabled -> everything works headerless."""
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    main.reset_state()
    c = TestClient(main.app)
    resp = c.post("/api/accounts", json={})
    assert resp.status_code == 200
    acct = resp.json()["account_id"]
    assert resp.json()["owner_user_id"] == "dev-user"
    resp = c.get(f"/api/accounts/{acct}/portfolio")
    assert resp.status_code == 200
    main.reset_state()


def test_dev_mode_claims_pre_ownership_accounts(monkeypatch):
    """Accounts with a blank owner (created before ownership) are claimed by
    the single dev user instead of 403ing."""
    from app.modes import Mode

    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    main.reset_state()
    store = main.get_store()
    legacy = Account(id="legacy-1", email=None, cash=Decimal("100"),
                     initial_cash=Decimal("100"),
                     created_at=datetime.now(UTC),
                     owner_user_id="", mode=Mode.EXPERIMENTAL)
    store.accounts["legacy-1"] = legacy
    c = TestClient(main.app)
    resp = c.get("/api/accounts/legacy-1/portfolio")
    assert resp.status_code == 200
    main.reset_state()


def test_public_endpoints_need_no_auth(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/billing/credits/packs").status_code == 200
    # Auth-protected: quotes stay public, agents/activity does not.
    assert client.get("/api/agents/activity").status_code == 401
