"""Store extensions for v2.1: user profiles and approval requests.

RED phase: pins the new store contracts before implementation.
- ``UserProfile``: the LearningAgent's picture of the user (risk, horizon,
  preferences, decision history) — one per account.
- ``ApprovalRequest``: the human-confirmation gate's pending decisions.
"""

from decimal import Decimal

from app.store import ApprovalRequest, InMemoryStore, UserProfile


def test_store_saves_and_loads_user_profile():
    store = InMemoryStore()
    account = store.create_account(email=None)
    profile = store.save_profile(
        UserProfile(
            account_id=account.id,
            risk="low",
            horizon_years=5.0,
            preferences={"likes": "dividends"},
        )
    )
    loaded = store.get_profile(account.id)
    assert loaded is not None
    assert loaded.risk == "low"
    assert loaded.horizon_years == 5.0
    assert loaded.preferences == {"likes": "dividends"}
    assert loaded.account_id == account.id
    assert profile.account_id == account.id


def test_store_profile_missing_returns_none():
    store = InMemoryStore()
    assert store.get_profile("nope") is None


def test_store_profile_update_replaces():
    store = InMemoryStore()
    account = store.create_account(email=None)
    store.save_profile(
        UserProfile(account_id=account.id, risk="low", horizon_years=5.0, preferences={})
    )
    store.save_profile(
        UserProfile(
            account_id=account.id, risk="high", horizon_years=1.0, preferences={}
        )
    )
    assert store.get_profile(account.id).risk == "high"


def test_store_approval_lifecycle():
    store = InMemoryStore()
    account = store.create_account(email=None)
    req = store.save_approval(
        ApprovalRequest(
            account_id=account.id,
            trades=[{"symbol": "AAPL", "side": "buy", "qty": "10"}],
            total_usd=Decimal("1500.00"),
            status="pending",
        )
    )
    assert req.id
    fetched = store.get_approval(req.id)
    assert fetched is not None and fetched.status == "pending"
    fetched.status = "approved"
    store.save_approval(fetched)
    assert store.get_approval(req.id).status == "approved"
    assert store.get_approval("nope") is None


def test_store_lists_pending_approvals():
    store = InMemoryStore()
    account = store.create_account(email=None)
    r1 = store.save_approval(
        ApprovalRequest(account_id=account.id, trades=[], total_usd=Decimal("0"), status="pending")
    )
    r2 = store.save_approval(
        ApprovalRequest(account_id=account.id, trades=[], total_usd=Decimal("0"), status="pending")
    )
    r2.status = "rejected"
    store.save_approval(r2)
    pending = store.list_approvals(account.id, status="pending")
    assert [r.id for r in pending] == [r1.id]
    assert len(store.list_approvals(account.id)) == 2
