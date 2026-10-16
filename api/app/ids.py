"""Shared identity/time helpers.

Extracted so ``app.orders`` and ``app.store`` can both use them without a
circular import. Re-exported from ``app.store`` for backward compatibility.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid4().hex[:12]
