"""Append-only audit log for money-affecting actions.

Adapted from Polygrow's ``AuditLogger`` (Supabase-backed there): every trade,
approval decision, and billing event is recorded with actor, timestamp, and
outcome. In-memory for v2.1 — the append-only contract is what matters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


@dataclass(frozen=True)
class AuditEntry:
    id: str
    created_at: datetime
    actor: str  # "executor" | "orchestrator" | "billing" | "user" | ...
    action: str  # e.g. "trade.executed", "approval.granted"
    account_id: str | None
    outcome: str  # "success" | "rejected" | "failed"
    details: dict = field(default_factory=dict)


class AuditLog:
    """In-memory append-only audit log. ``list()`` returns a snapshot in order."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def append(
        self,
        *,
        actor: str,
        action: str,
        account_id: str | None = None,
        outcome: str = "success",
        details: dict | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            id=uuid4().hex[:12],
            created_at=datetime.now(UTC),
            actor=actor,
            action=action,
            account_id=account_id,
            outcome=outcome,
            details=dict(details or {}),
        )
        self._entries.append(entry)
        return entry

    def list(
        self,
        *,
        account_id: str | None = None,
        action: str | None = None,
        limit: int | None = None,
    ) -> list[AuditEntry]:
        entries = [
            e
            for e in self._entries
            if (account_id is None or e.account_id == account_id)
            and (action is None or e.action == action)
        ]
        if limit is not None:
            entries = entries[-limit:]
        return list(entries)
