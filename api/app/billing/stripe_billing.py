"""Stripe billing for Finkow product subscriptions.

RULE: Stripe moves PRODUCT money (subscriptions / one-time payments), never
market orders. It is not a brokerage and never touches investing.

- ``StripeBilling`` wraps Checkout Sessions + webhook verification.
- Everything is behind ``STRIPE_SECRET_KEY`` presence: unconfigured → every
  operation raises ``BillingNotConfigured`` (the API answers 503).
- The ``stripe`` package is imported lazily so the service boots without it;
  tests inject a fake module — no live Stripe calls in tests, ever.
- The key itself is never logged or included in reprs (only a short hint).
"""

from __future__ import annotations

import importlib
import os


class BillingNotConfigured(Exception):
    """Stripe is not configured (no STRIPE_SECRET_KEY)."""


class StripeBilling:
    """Product billing via Stripe Checkout. Paper-safe by construction."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get(
            "STRIPE_SECRET_KEY"
        )

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    @property
    def key_hint(self) -> str:
        if not self._api_key:
            return ""
        return self._api_key[:8] + "..."

    def __repr__(self) -> str:
        return f"StripeBilling(configured={self.is_configured})"

    def _stripe(self):
        if not self.is_configured:
            raise BillingNotConfigured(
                "STRIPE_SECRET_KEY is not set — billing is disabled"
            )
        try:
            return importlib.import_module("stripe")
        except ImportError as exc:
            raise BillingNotConfigured(
                "stripe package is not installed"
            ) from exc

    def create_checkout_session(
        self,
        *,
        price_id: str,
        success_url: str,
        cancel_url: str,
        customer_email: str | None = None,
        mode: str = "subscription",
    ) -> dict:
        """Create a Checkout Session for a product price. Never a market order."""
        if mode not in ("subscription", "payment"):
            raise ValueError(f"mode must be 'subscription' or 'payment', got {mode!r}")
        stripe = self._stripe()
        params: dict = {
            "mode": mode,
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
        }
        if customer_email:
            params["customer_email"] = customer_email
        session = stripe.checkout.Session.create(**params)
        if isinstance(session, dict):
            sid, url = session.get("id"), session.get("url")
        else:
            sid, url = session.id, session.url
        return {"id": sid, "url": url, "mode": mode}

    def handle_webhook(
        self, *, payload: bytes, signature: str, webhook_secret: str | None
    ) -> dict:
        """Verify a Stripe webhook signature and return the normalized event.

        Skeleton: verifies authenticity; fulfillment (granting the
        subscription) is product logic the caller owns.
        """
        stripe = self._stripe()
        secret = webhook_secret or os.environ.get("STRIPE_WEBHOOK_SECRET")
        try:
            event = stripe.Webhook.construct_event(payload, signature, secret)
        except Exception as exc:
            raise ValueError(f"webhook signature verification failed: {exc}") from exc
        if isinstance(event, dict):
            return {"type": event.get("type"), "data": event.get("data", {})}
        return {"type": getattr(event, "type", None), "data": getattr(event, "data", {})}
