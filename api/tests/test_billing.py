"""Stripe billing: product subscriptions via Checkout Sessions + webhooks.

RED phase: pins the billing contract before implementation. Everything is
behind STRIPE_SECRET_KEY presence; tests inject a fake ``stripe`` module —
no live calls, ever, in tests.

Documented rule: Stripe moves PRODUCT money (subscriptions), never market
orders. It is not a brokerage.
"""

import sys
import types

import pytest

from app.billing.stripe_billing import BillingNotConfigured, StripeBilling


def _install_fake_stripe(monkeypatch):
    """Fake the ``stripe`` package: records calls, returns canned objects."""
    fake = types.ModuleType("stripe")
    calls = []

    class FakeSession:
        @staticmethod
        def create(**kwargs):
            calls.append(("Session.create", kwargs))
            return {"id": "cs_test_123", "url": "https://checkout.stripe.test/pay/123"}

    class FakeCheckout:
        Session = FakeSession

    class FakeWebhook:
        @staticmethod
        def construct_event(payload, signature, secret):
            calls.append(("Webhook.construct_event", signature))
            if signature != "valid-sig":
                raise ValueError("invalid signature")
            return {"type": "checkout.session.completed", "data": {"id": "cs_test_123"}}

    fake.checkout = FakeCheckout
    fake.Webhook = FakeWebhook
    monkeypatch.setitem(sys.modules, "stripe", fake)
    return calls


def test_billing_reports_not_configured_without_key(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    billing = StripeBilling(api_key=None)
    assert billing.is_configured is False
    with pytest.raises(BillingNotConfigured):
        billing.create_checkout_session(
            price_id="price_123",
            success_url="https://x.test/ok",
            cancel_url="https://x.test/no",
        )


def test_billing_creates_checkout_session_when_configured(monkeypatch):
    calls = _install_fake_stripe(monkeypatch)
    billing = StripeBilling(api_key="sk_test_fake")
    assert billing.is_configured is True
    session = billing.create_checkout_session(
        price_id="price_123",
        success_url="https://x.test/ok",
        cancel_url="https://x.test/no",
        customer_email="user@example.com",
    )
    assert session["id"] == "cs_test_123"
    assert session["url"].startswith("https://")
    (name, kwargs), = calls
    assert name == "Session.create"
    assert kwargs["mode"] == "subscription"
    assert "price_123" in str(kwargs)


def test_billing_supports_one_time_mode(monkeypatch):
    calls = _install_fake_stripe(monkeypatch)
    billing = StripeBilling(api_key="sk_test_fake")
    billing.create_checkout_session(
        price_id="price_123",
        success_url="https://x.test/ok",
        cancel_url="https://x.test/no",
        mode="payment",
    )
    assert calls[0][1]["mode"] == "payment"


def test_billing_rejects_unknown_mode(monkeypatch):
    _install_fake_stripe(monkeypatch)
    billing = StripeBilling(api_key="sk_test_fake")
    with pytest.raises(ValueError, match="mode"):
        billing.create_checkout_session(
            price_id="price_123",
            success_url="https://x.test/ok",
            cancel_url="https://x.test/no",
            mode="bogus",
        )


def test_webhook_verifies_signature(monkeypatch):
    _install_fake_stripe(monkeypatch)
    billing = StripeBilling(api_key="sk_test_fake")
    event = billing.handle_webhook(
        payload=b'{"id":"evt_1"}',
        signature="valid-sig",
        webhook_secret="whsec_fake",
    )
    assert event["type"] == "checkout.session.completed"


def test_webhook_rejects_bad_signature(monkeypatch):
    _install_fake_stripe(monkeypatch)
    billing = StripeBilling(api_key="sk_test_fake")
    with pytest.raises(ValueError, match="signature"):
        billing.handle_webhook(
            payload=b'{"id":"evt_1"}',
            signature="bad-sig",
            webhook_secret="whsec_fake",
        )


def test_webhook_requires_configuration(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    billing = StripeBilling(api_key=None)
    with pytest.raises(BillingNotConfigured):
        billing.handle_webhook(payload=b"{}", signature="x", webhook_secret="y")


def test_billing_reads_key_from_environment(monkeypatch):
    _install_fake_stripe(monkeypatch)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_from_env")
    billing = StripeBilling()
    assert billing.is_configured is True
    assert billing.key_hint == "sk_test_from_env"[:8] + "..."
    # never expose the full key
    assert "sk_test_from_env" not in repr(billing)
