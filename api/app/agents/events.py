"""Append-only agent activity log.

Every agent step writes an event here. The log is the backbone of the sentient
UI (activity feed) and of trust-through-transparency: nothing an agent does is
invisible. In-memory for v2 (same caveat as the store); the append-only
contract is what matters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


@dataclass(frozen=True)
class AgentEvent:
    id: str
    created_at: datetime
    agent: str  # "planner" | "radar" | "pilot" | "explainer" | ...
    kind: str  # e.g. "plan.generated"
    payload: dict = field(default_factory=dict)


class EventLog:
    """In-memory append-only log. ``list()`` returns a snapshot in order."""

    def __init__(self) -> None:
        self._events: list[AgentEvent] = []

    def append(self, agent: str, kind: str, payload: dict | None = None) -> AgentEvent:
        event = AgentEvent(
            id=uuid4().hex[:12],
            created_at=datetime.now(UTC),
            agent=agent,
            kind=kind,
            payload=dict(payload or {}),
        )
        self._events.append(event)
        return event

    def list(self, *, agent: str | None = None, limit: int | None = None) -> list[AgentEvent]:
        events = [e for e in self._events if agent is None or e.agent == agent]
        if limit is not None:
            events = events[-limit:]
        return list(events)
