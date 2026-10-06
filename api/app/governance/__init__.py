"""Governance layer (adapted from Polygrow's governance_layer).

In-memory instead of Redis/Supabase — no new infrastructure for the MVP.
- ``pii_filter``: detect + redact PII in stored user text.
- ``rate_limiter``: token-bucket guard for paid AIsa calls.
- ``verifier``: schema + safety checks on agent outputs (deterministic; no LLM
  round-trip — adaptation note vs Polygrow).
- ``audit``: append-only log of money-affecting actions.
"""

from app.governance.audit import AuditEntry, AuditLog
from app.governance.pii_filter import PIIFilter
from app.governance.rate_limiter import RateLimiter, RateLimitExceeded, wrap_port
from app.governance.verifier import OutputVerifier, VerificationResult

__all__ = [
    "AuditEntry",
    "AuditLog",
    "OutputVerifier",
    "PIIFilter",
    "RateLimiter",
    "RateLimitExceeded",
    "VerificationResult",
    "wrap_port",
]
