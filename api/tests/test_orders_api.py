"""HTTP surface for the order lifecycle: create, idempotency, detail,
listing, and reconciliation."""

import asyncio
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import main
from app.brokerage import (
    LiveTradingDisabledError,
    MockBrokerage,
    OrderSide,
)
from app.modes import Mode
from tests.test_api import make_test_client


@pytest.fixture()
def client():
    c = make_test_client()
    yield c
    main.app.dependency_overrides.clear()


def _account(c: TestClient) -> str:
    return c.post("/api/accounts", json={}).json()["account_id"]


def _buy(c: TestClient, account_id: str, headers: dict | None = None,
         qty: str = "10"):
    return c.post(
        "/api/orders",
        json={
            "account_id": account_id,
            "symbol": "AAPL",
            "side": "buy",
            "quantity": qty,
        },
        headers=headers or {},
    )


def test_place_order_returns_explicit_lifecycle_state(client):
    c = client
    account_id = _account(c)
    body = _buy(c, account_id).json()
    assert body["status"] == "filled"
    assert body["simulated"] is True  # mock fill, never presented as real
    assert body["mode"] == "experimental"
    assert body["virtual"] is True
    assert body["provider_order_id"] is None
    assert body["order_id"]
    assert body["transaction_id"]
    # backward compatible fields still present
    assert body["cash_after"] == "98500.00"


def test_unknown_symbol_records_rejected_order(client):
    c = client
    account_id = _account(c)
    resp = c.post(
        "/api/orders",
        json={
            "account_id": account_id,
            "symbol": "NOPE",
            "side": "buy",
            "quantity": "1",
        },
    )
    assert resp.status_code == 404
    orders = c.get(f"/api/accounts/{account_id}/orders").json()["orders"]
    assert len(orders) == 1
    assert orders[0]["status"] == "rejected"
    assert "unknown symbol" in orders[0]["reject_reason"].lower()


def test_place_order_idempotency_key_replay_returns_original(client):
    c = client
    account_id = _account(c)
    headers = {"Idempotency-Key": "order-abc-123"}
    first = _buy(c, account_id, headers).json()
    second = _buy(c, account_id, headers).json()
    assert second["order_id"] == first["order_id"]
    assert second["idempotent_replay"] is True
    assert first.get("idempotent_replay", False) is False
    # the trade happened exactly once: cash moved once
    pf = c.get(f"/api/accounts/{account_id}/portfolio").json()
    assert pf["cash"] == "98500.00"


def test_place_order_without_key_creates_distinct_orders(client):
    c = client
    account_id = _account(c)
    first = _buy(c, account_id).json()
    second = _buy(c, account_id).json()
    assert second["order_id"] != first["order_id"]


def test_insufficient_funds_records_rejected_order(client):
    c = client
    account_id = _account(c)
    # spend down to $10k with six $15k buys (each under the $25k limit)
    for _ in range(6):
        assert _buy(c, account_id, qty="100").status_code == 200
    # a $15k buy now exceeds the $10k cash: execution fails -> rejected order
    resp = _buy(c, account_id, qty="100")
    assert resp.status_code == 400
    assert "insufficient" in resp.json()["detail"].lower()
    # the failed order is recorded as rejected, not silently dropped
    orders = c.get(f"/api/accounts/{account_id}/orders").json()["orders"]
    rejected = [o for o in orders if o["status"] == "rejected"]
    assert len(rejected) == 1
    assert rejected[0]["simulated"] is True
    assert "insufficient" in rejected[0]["reject_reason"].lower()


def test_max_trade_usd_breach_records_rejected_order(client):
    c = client
    account_id = _account(c)
    resp = c.post(
        "/api/orders",
        json={
            "account_id": account_id,
            "symbol": "BTC",
            "side": "buy",
            "quantity": "1",  # $60k > $25k limit
        },
    )
    assert resp.status_code == 400
    assert "max_trade_usd" in resp.json()["detail"]
    orders = c.get(f"/api/accounts/{account_id}/orders").json()["orders"]
    assert len(orders) == 1
    assert orders[0]["status"] == "rejected"
    assert "max_trade_usd" in orders[0]["reject_reason"]


def test_get_order_detail_and_list_orders(client):
    c = client
    account_id = _account(c)
    placed = _buy(c, account_id).json()
    detail = c.get(f"/api/orders/{placed['order_id']}").json()
    assert detail["id"] == placed["order_id"]
    assert detail["status"] == "filled"
    assert detail["simulated"] is True
    assert detail["mode"] == "experimental"
    assert detail["symbol"] == "AAPL"
    listed = c.get(f"/api/accounts/{account_id}/orders").json()["orders"]
    assert [o["id"] for o in listed] == [placed["order_id"]]


def test_get_unknown_order_is_404(client):
    assert client.get("/api/orders/nope").status_code == 404


def test_reconcile_filled_order_is_consistent(client):
    c = client
    account_id = _account(c)
    placed = _buy(c, account_id).json()
    report = c.post(f"/api/orders/{placed['order_id']}/reconcile").json()
    assert report["recorded_status"] == "filled"
    assert report["consistent"] is True
    assert report["simulated"] is True


def test_transactions_carry_order_lifecycle_fields(client):
    c = client
    account_id = _account(c)
    placed = _buy(c, account_id).json()
    txns = c.get(f"/api/accounts/{account_id}/transactions").json()["transactions"]
    assert len(txns) == 1
    txn = txns[0]
    assert txn["order_id"] == placed["order_id"]
    assert txn["status"] == "filled"
    assert txn["simulated"] is True


def test_brokerage_order_is_labeled_simulated_with_no_provider_id(client):
    c = client
    resp = c.post(
        "/api/brokerage/orders",
        json={"symbol": "AAPL", "qty": "1", "side": "buy"},
        headers={"Idempotency-Key": "brk-1"},
    )
    body = resp.json()
    assert body["status"] == "filled"
    assert body["simulated"] is True
    assert body["provider_order_id"] is None
    assert body["mode"] == "experimental"
    replay = c.post(
        "/api/brokerage/orders",
        json={"symbol": "AAPL", "qty": "1", "side": "buy"},
        headers={"Idempotency-Key": "brk-1"},
    ).json()
    assert replay["id"] == body["id"]


def test_brokerage_real_mode_never_submits(client):
    # The mock brokerage is experimental-only; a real-mode attempt fails loud.
    broker = MockBrokerage(mode=Mode.REAL)
    with pytest.raises(LiveTradingDisabledError):
        asyncio.run(broker.submit_order("AAPL", Decimal("1"), OrderSide.BUY))
