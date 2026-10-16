"""SupabaseStore adapter skeleton.

Tested with mocked HTTP (httpx.MockTransport) — zero live calls. The real
Supabase project is pending on Roger, so anything beyond the core account /
position / transaction / order surface raises ``SupabaseNotImplementedError``
honestly instead of pretending to work.
"""

from decimal import Decimal

import httpx
import pytest

from app.modes import Mode
from app.orders import Order, OrderStatus
from app.store import STARTING_CASH, ApprovalRequest, utcnow
from app.supabase_store import (
    SupabaseConfigError,
    SupabaseNotImplementedError,
    SupabaseStore,
)

BASE = "https://xyzcompany.supabase.co"
KEY = "service-role-key"


def make_store(handler, monkeypatch) -> SupabaseStore:
    monkeypatch.setenv("SUPABASE_URL", BASE)
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", KEY)
    transport = httpx.MockTransport(handler)
    return SupabaseStore(transport=transport)


def test_missing_env_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    with pytest.raises(SupabaseConfigError) as exc:
        SupabaseStore()
    assert "SUPABASE_URL" in str(exc.value)
    assert "Roger" in str(exc.value) or "pending" in str(exc.value).lower()


def test_create_account_posts_to_rest(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["apikey"] = request.headers.get("apikey")
        assert request.headers["authorization"] == f"Bearer {KEY}"
        return httpx.Response(201, json=[{
            "id": "acc-1", "email": "a@b.c", "cash": "100000.00",
            "initial_cash": "100000.00", "owner_user_id": "user-1",
            "mode": "experimental", "created_at": "2026-10-16T00:00:00+00:00",
        }])

    store = make_store(handler, monkeypatch)
    acct = store.create_account("a@b.c", owner_user_id="user-1")
    assert seen["method"] == "POST"
    assert seen["url"] == f"{BASE}/rest/v1/accounts"
    assert seen["apikey"] == KEY
    assert acct.id == "acc-1"
    assert acct.owner_user_id == "user-1"
    assert acct.mode is Mode.EXPERIMENTAL
    assert acct.cash == STARTING_CASH


def test_get_account_missing_returns_none(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    store = make_store(handler, monkeypatch)
    assert store.get_account("nope") is None


def test_get_positions_round_trip(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rest/v1/positions"
        return httpx.Response(200, json=[{
            "account_id": "acc-1", "symbol": "AAPL", "qty": "10",
            "avg_cost": "150.00", "mode": "experimental",
        }])

    store = make_store(handler, monkeypatch)
    positions = store.get_positions("acc-1")
    assert len(positions) == 1
    assert positions[0].qty == Decimal("10")
    assert positions[0].mode is Mode.EXPERIMENTAL


def test_rest_errors_surface(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "boom"})

    store = make_store(handler, monkeypatch)
    with pytest.raises(Exception) as exc:
        store.get_account("acc-1")
    assert "boom" in str(exc.value)


def test_unimplemented_surface_is_honest(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no HTTP should happen for unimplemented methods")

    store = make_store(handler, monkeypatch)
    with pytest.raises(SupabaseNotImplementedError):
        store.create_goal("x", Decimal("1"), "acc-1")
    with pytest.raises(SupabaseNotImplementedError):
        store.save_approval(ApprovalRequest(
            account_id="acc-1", trades=[], total_usd=Decimal("0")))


def test_order_upsert_and_get_round_trip(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["prefer"] = request.headers.get("prefer")
        if request.method == "POST":
            return httpx.Response(201, json=[])
        return httpx.Response(200, json=[{
            "id": "ord-1", "account_id": "acc-1", "symbol": "AAPL",
            "side": "buy", "qty": "10", "order_type": "market",
            "time_in_force": "day", "status": "filled", "filled_qty": "10",
            "avg_fill_price": "150.00", "provider_order_id": None,
            "simulated": True, "idempotency_key": "k-1",
            "approval_id": None, "reject_reason": None,
            "mode": "experimental",
            "created_at": "2026-10-16T00:00:00+00:00",
            "updated_at": "2026-10-16T00:00:01+00:00",
        }])

    store = make_store(handler, monkeypatch)
    order = Order(
        id="ord-1", account_id="acc-1", symbol="AAPL", side="buy",
        qty=Decimal("10"), idempotency_key="k-1", created_at=utcnow(),
        updated_at=utcnow(),
    )
    store.save_order(order)  # upsert: must not raise on mocked 201
    assert seen["method"] == "POST"
    assert "merge-duplicates" in (seen["prefer"] or "")

    fetched = store.get_order("ord-1")
    assert fetched is not None
    assert fetched.status is OrderStatus.FILLED
    assert fetched.simulated is True
    assert fetched.provider_order_id is None
    assert fetched.idempotency_key == "k-1"

    listed = store.list_orders("acc-1")
    assert [o.id for o in listed] == ["ord-1"]
    by_key = store.get_order_by_idempotency_key("acc-1", "k-1")
    assert by_key is not None and by_key.id == "ord-1"


def test_list_accounts_by_owner_filters(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "owner_user_id" in str(request.url)
        return httpx.Response(200, json=[{
            "id": "acc-1", "email": "a@b.c", "cash": "100000.00",
            "initial_cash": "100000.00", "owner_user_id": "user-1",
            "mode": "experimental", "created_at": "2026-10-16T00:00:00+00:00",
        }])

    store = make_store(handler, monkeypatch)
    accounts = store.list_accounts_by_owner("user-1")
    assert [a.id for a in accounts] == ["acc-1"]
