"""v2 compatibility facade: goal planning now lives in ``LearningAgent``.

The logic moved to :mod:`app.agents.learning` (not duplicated). This module
re-exports the v2 names and keeps the exact v2 event stream
("planner"/"goal.received"/"plan.generated") so existing callers and tests
keep working unchanged.
"""

from __future__ import annotations

from app.agents.events import EventLog
from app.agents.learning import (
    Allocation,
    GoalSpec,
    LearningAgent,
    Plan,
    parse_goal,
)
from app.ports import LLMPort

__all__ = ["Allocation", "GoalPlanner", "GoalSpec", "Plan", "parse_goal"]


class GoalPlanner:
    """Thin facade over :class:`LearningAgent` preserving the v2 contract."""

    def __init__(self, llm: LLMPort, events: EventLog | None = None) -> None:
        self._agent = LearningAgent(llm, store=None, events=events, agent_name="planner")

    async def plan(self, goal_text: str) -> Plan:
        return await self._agent.plan_goal(goal_text)
