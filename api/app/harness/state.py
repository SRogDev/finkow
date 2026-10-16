"""Run state for the orchestrator harness.

Adapted from Polygrow's ``ai_mind/state.py``: a single state object flows
through the stages (entry -> context_gather -> intent_classify -> delegate ->
verify -> synthesize -> memory_write), accumulating results, checkpoints, and
— when the orchestrator cannot proceed alone — a human question.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class RunState:
    run_id: str = field(default_factory=lambda: uuid4().hex[:12])
    intent: str = "unknown"
    confidence: float = 0.0
    account_id: str | None = None
    text: str = ""
    stages: list[str] = field(default_factory=list)
    results: dict = field(default_factory=dict)
    requires_human: bool = False
    human_question: str | None = None
    error: str | None = None
    checkpoints: list[dict] = field(default_factory=list)
