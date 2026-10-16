"""Governance layer: PII filter, rate limiter, output verifier, audit log.

RED phase: pins the governance contracts before implementation. Adapted from
Polygrow's governance_layer (in-memory instead of Redis/Supabase — no new
infrastructure for the MVP).
"""

import asyncio
import time

import pytest

from app.governance.audit import AuditLog
from app.governance.pii_filter import PIIFilter
from app.governance.rate_limiter import RateLimiter
from app.governance.verifier import OutputVerifier

# ---------------------------------------------------------------- PII filter


def test_pii_filter_detects_email_phone_and_card():
    f = PIIFilter()
    text = "reach me at roger@example.com or 555-123-4567, card 4111 1111 1111 1111"
    findings = f.detect_pii(text)
    kinds = {x["type"] for x in findings}
    assert {"email", "phone", "credit_card"} <= kinds


def test_pii_filter_redacts_without_leaking_values():
    f = PIIFilter()
    redacted = f.redact("email roger@example.com please")
    assert "roger@example.com" not in redacted
    assert "[EMAIL_REDACTED]" in redacted


def test_pii_filter_clean_text_passes_through():
    f = PIIFilter()
    text = "grow $1,000 over 5 years, low risk"
    assert f.redact(text) == text
    assert not f.contains_pii(text)


def test_pii_filter_redacts_nested_mappings():
    f = PIIFilter()
    out = f.redact_mapping({"goal": {"text": "call 555-123-4567"}, "n": 3})
    assert out["goal"]["text"] == "call [PHONE_REDACTED]"
    assert out["n"] == 3


# ---------------------------------------------------------------- rate limiter


def test_rate_limiter_allows_up_to_limit_then_blocks():
    rl = RateLimiter(max_calls=3, window_seconds=60)
    assert rl.acquire("aisa")
    assert rl.acquire("aisa")
    assert rl.acquire("aisa")
    assert not rl.acquire("aisa")


def test_rate_limiter_is_per_key():
    rl = RateLimiter(max_calls=1, window_seconds=60)
    assert rl.acquire("key-a")
    assert not rl.acquire("key-a")
    assert rl.acquire("key-b")


def test_rate_limiter_window_resets():
    rl = RateLimiter(max_calls=1, window_seconds=0.05)
    assert rl.acquire("k")
    assert not rl.acquire("k")
    time.sleep(0.06)
    assert rl.acquire("k")


def test_rate_limiter_reports_remaining():
    rl = RateLimiter(max_calls=2, window_seconds=60)
    rl.acquire("k")
    status = rl.status("k")
    assert status["remaining"] == 1
    assert status["limit"] == 2


def test_wrap_port_enforces_budget_and_raises_provider_error():
    from app.governance import RateLimitExceeded, wrap_port
    from app.ports import ProviderError
    from app.providers.mock import MockMarketData

    rl = RateLimiter(max_calls=1, window_seconds=60)
    guarded = wrap_port(MockMarketData(), rl, "aisa")
    assert guarded.name == "mock"

    async def go():
        await guarded.get_quote("AAPL")  # 1st: ok
        await guarded.get_quote("AAPL")  # 2nd: over budget

    with pytest.raises(RateLimitExceeded):
        asyncio.run(go())
    # it composes with fallback chains
    assert issubclass(RateLimitExceeded, ProviderError)


# ---------------------------------------------------------------- verifier


def test_verifier_passes_valid_schema():
    v = OutputVerifier()
    result = v.verify(
        {"symbol": "AAPL", "score": 82.5},
        required={"symbol": str, "score": float},
    )
    assert result.passed is True
    assert result.output == {"symbol": "AAPL", "score": 82.5}


def test_verifier_rejects_missing_and_mistyped_fields():
    v = OutputVerifier()
    missing = v.verify({"symbol": "AAPL"}, required={"symbol": str, "score": float})
    assert missing.passed is False
    assert missing.output is None
    mistyped = v.verify(
        {"symbol": "AAPL", "score": "high"}, required={"symbol": str, "score": float}
    )
    assert mistyped.passed is False


def test_verifier_rejects_pii_in_output():
    v = OutputVerifier()
    result = v.verify({"note": "contact roger@example.com"}, required={"note": str})
    assert result.passed is False
    assert any("pii" in e.lower() for e in result.errors)


def test_verifier_rejects_guaranteed_returns_language():
    v = OutputVerifier()
    result = v.verify(
        {"reasoning": "this is a guaranteed profit, risk-free win"},
        required={"reasoning": str},
    )
    assert result.passed is False
    assert any("guarantee" in e.lower() for e in result.errors)


def test_verifier_allows_honest_plain_language():
    v = OutputVerifier()
    result = v.verify(
        {"reasoning": "Steady earner; prices can still fall."},
        required={"reasoning": str},
    )
    assert result.passed is True


# ---------------------------------------------------------------- audit log


def test_audit_log_records_money_affecting_actions():
    log = AuditLog()
    entry = log.append(
        actor="executor",
        action="trade.executed",
        account_id="acc1",
        details={"symbol": "AAPL", "qty": "10", "price": "150.00"},
    )
    assert entry.id
    assert entry.created_at is not None
    assert entry.outcome == "success"
    entries = log.list(account_id="acc1")
    assert len(entries) == 1
    assert entries[0].action == "trade.executed"


def test_audit_log_filters_and_orders():
    log = AuditLog()
    log.append(actor="executor", action="trade.executed", account_id="a1")
    log.append(actor="executor", action="approval.rejected", account_id="a2")
    log.append(actor="orchestrator", action="run.completed", account_id="a1")
    assert len(log.list()) == 3
    assert len(log.list(account_id="a1")) == 2
    assert len(log.list(action="trade.executed")) == 1
    # newest last (append-only order preserved)
    assert [e.action for e in log.list(account_id="a1")] == [
        "trade.executed",
        "run.completed",
    ]


def test_audit_log_records_failures_with_outcome():
    log = AuditLog()
    log.append(
        actor="executor",
        action="trade.rejected",
        account_id="a1",
        outcome="rejected",
        details={"reason": "limit exceeded"},
    )
    assert log.list(action="trade.rejected")[0].outcome == "rejected"
