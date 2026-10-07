"""Agent money layer, part 2: Stripe credit packs, HTTP endpoints, E2E.

Continues tests/test_agent_money.py (same RED phase).
"""

import asyncio
import sys
import types

import pytest
from fastapi.testclient import TestClient

from app import main


def _run(coro):
    return asyncio.run(coro)


def _install_fake_stripe_credits(monkeypatch, event=None):
    fake = types.ModuleType("stripe")
    calls = []
    state = {"event": event}

    class FakeSession:
        @staticmethod
        def create(**kwargs):
            calls.append(("Session.create", kwargs))
            return {"id": "cs_test_credits_1", "url": "https://checkout.stripe.test/pay/c1"}

    class FakeCheckout:
        Session = FakeSession

    class FakeWebhook:
        @staticmethod
        def construct_event(payload, signature, secret):
            calls.append(("Webhook.construct_event", signature))
            if signature != "valid-sig":
                raise ValueError("invalid signature")
            return state["event"] or {"type": "checkout.session.completed", "data": {}}

    fake.checkout = FakeCheckout
    fake.Webhook = FakeWebhook
    monkeypatch.setitem(sys.modules, "stripe", fake)
    return calls


def _credits_event(account_id, credits=5000, session_id="cs_test_credits_1"):
    return {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id,
                "amount_total": 500,
                "metadata": {
                    "kind": "credits",
                    "account_id": account_id,
                    "pack_id": "credits_5",
                    "credits": str(credits),
                },
            }
        },
    }


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    _install_fake_stripe_credits(monkeypatch)
    main.reset_state()
    from app.governance import metering as metering_mod

    metering_mod.reset_metering()
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


# ------------------------------------------------------------------ checkout


def test_credits_checkout_creates_payment_session(monkeypatch):
    calls = _install_fake_stripe_credits(monkeypatch)
    from app.billing.stripe_billing import StripeBilling

    billing = StripeBilling(api_key="sk_test_fake")
    session = billing.create_credits_checkout_session(
        pack_id="credits_5",
        account_id="acct-1",
        success_url="https://x.test/ok",
        cancel_url="https://x.test/no",
    )
    assert session["id"] == "cs_test_credits_1"
    (name, kwargs), = calls
    assert name == "Session.create"
    assert kwargs["mode"] == "payment"
    line = kwargs["line_items"][0]
    assert line["price_data"]["unit_amount"] == 500  # $5 pack
    assert line["price_data"]["currency"] == "usd"
    meta = kwargs["metadata"]
    assert meta["kind"] == "credits"
    assert meta["account_id"] == "acct-1"
    assert meta["credits"] == "5000"


def test_credits_checkout_unknown_pack():
    from app.billing.stripe_billing import StripeBilling

    billing = StripeBilling(api_key="sk_test_fake")
    with pytest.raises(ValueError, match="pack"):
        billing.create_credits_checkout_session(
            pack_id="nope",
            account_id="acct-1",
            success_url="https://x.test/ok",
            cancel_url="https://x.test/no",
        )


def test_credits_checkout_503_when_unconfigured(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    from app.billing.stripe_billing import BillingNotConfigured, StripeBilling

    billing = StripeBilling(api_key=None)
    with pytest.raises(BillingNotConfigured):
        billing.create_credits_checkout_session(
            pack_id="credits_5",
            account_id="acct-1",
            success_url="https://x.test/ok",
            cancel_url="https://x.test/no",
        )


def test_credits_checkout_http_503_without_key(client, monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    acct = client.post("/api/accounts", json={}).json()["account_id"]
    r = client.post(
        "/api/billing/credits/checkout",
        json={"account_id": acct, "pack_id": "credits_5",
              "success_url": "https://x.test/ok", "cancel_url": "https://x.test/no"},
    )
    assert r.status_code == 503


def test_credits_checkout_http(client):
    acct = client.post("/api/accounts", json={}).json()["account_id"]
    r = client.post(
        "/api/billing/credits/checkout",
        json={"account_id": acct, "pack_id": "credits_20",
              "success_url": "https://x.test/ok", "cancel_url": "https://x.test/no"},
    )
    assert r.status_code == 200
    assert r.json()["url"].startswith("https://")


def test_credits_packs_endpoint(client):
    packs = client.get("/api/billing/credits/packs").json()["packs"]
    by_id = {p["pack_id"]: p for p in packs}
    assert by_id["credits_5"]["usd"] == "5.00"
    assert by_id["credits_5"]["credits"] == 5000


def test_credits_balance_endpoint(client):
    acct = client.post("/api/accounts", json={}).json()["account_id"]
    bal = client.get(f"/api/billing/credits/balance?account_id={acct}").json()
    assert bal["balance_credits"] == 0
    assert bal["balance_usd"] == "0.00"


# ------------------------------------------------------------------ webhook


def test_webhook_credits_fulfillment(client, monkeypatch):
    from app.billing.credits import get_ledger

    acct = client.post("/api/accounts", json={}).json()["account_id"]
    _install_fake_stripe_credits(monkeypatch, event=_credits_event(acct))
    r = client.post(
        "/api/billing/webhook",
        content=b'{"id":"evt_1"}',
        headers={"stripe-signature": "valid-sig"},
    )
    assert r.status_code == 200
    assert get_ledger().balance(acct) == 5000
    bal = client.get(f"/api/billing/credits/balance?account_id={acct}").json()
    assert bal["balance_credits"] == 5000
    assert bal["balance_usd"] == "5.00"


def test_webhook_credits_idempotent_on_replay(client, monkeypatch):
    from app.billing.credits import get_ledger

    acct = client.post("/api/accounts", json={}).json()["account_id"]
    _install_fake_stripe_credits(monkeypatch, event=_credits_event(acct))
    for _ in range(2):
        r = client.post(
            "/api/billing/webhook",
            content=b'{"id":"evt_1"}',
            headers={"stripe-signature": "valid-sig"},
        )
        assert r.status_code == 200
    assert get_ledger().balance(acct) == 5000  # credited exactly once


def test_webhook_ignores_non_credit_events(client, monkeypatch):
    from app.billing.credits import get_ledger

    acct = client.post("/api/accounts", json={}).json()["account_id"]
    _install_fake_stripe_credits(
        monkeypatch,
        event={"type": "customer.subscription.created", "data": {"object": {"id": "sub_1"}}},
    )
    r = client.post(
        "/api/billing/webhook",
        content=b'{"id":"evt_2"}',
        headers={"stripe-signature": "valid-sig"},
    )
    assert r.status_code == 200
    assert get_ledger().balance(acct) == 0  # subscription path untouched


# ------------------------------------------------------------------ 402


def test_explain_402_when_credits_exhausted(client, monkeypatch):
    """Paid LLM blocked by empty balance -> 402 with top-up link."""
    from app.billing.credits import get_ledger
    from app.governance.metering import MeteredPort, SpendingGovernor

    class PaidLLM:
        name = "paid-fake-llm"
        last_cost_micros_usd = 5000

        async def complete(self, messages, *, system="", json_mode=False):
            raise AssertionError("must not be called without credits")

    ledger = get_ledger()
    gov = SpendingGovernor(ledger, daily_cap_credits=1000, monthly_cap_credits=10000)
    main.app.dependency_overrides[main.get_llm] = lambda: MeteredPort(
        PaidLLM(), ledger=ledger, governor=gov, tool="test.llm", estimate_micros=10000
    )
    acct = client.post("/api/accounts", json={}).json()["account_id"]
    # zero credits on the account -> the paid call is refused up front
    r = client.post("/api/explain", json={"account_id": acct, "question": "why?"})
    assert r.status_code == 402
    body = r.json()["detail"]
    assert "top_up" in body and "packs" in body


# ------------------------------------------------------------------ E2E
