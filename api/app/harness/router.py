"""Intent router with confidence-threshold routing.

Adapted from Polygrow's ``ai_mind/router.py``: ``CONFIDENCE_THRESHOLD = 0.6``.
Below it, the orchestrator must not act — it asks for clarification (the
human-interrupt pattern). Classification is deterministic keyword scoring:
fast, testable, no paid LLM call for routing.
"""

from __future__ import annotations

from app.harness.state import RunState

CONFIDENCE_THRESHOLD = 0.6

_INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "invest": (
        "invest", "buy", "goal", "plan", "portfolio", "allocate", "retirement",
        "grow $", "grow my",
    ),
    "opportunities": (
        "opportunit", "hunt", "scan", "find", "screener", "what's hot",
        "what is hot",
    ),
    "analyze": (
        "analy", "valuation", "fundamental", "risk", "p/e", "filing",
        "earnings", "balance sheet",
    ),
    "explain": (
        "why", "explain", "what happened", "how is", "how's", "move", "moved",
    ),
    "learn": (
        "teach", "learn", "what is", "what's", "explain like",
        "diversification", "etf",
    ),
}


def classify_intent(text: str) -> tuple[str, float]:
    """Return (intent, confidence) from keyword scoring.

    Strong multi-keyword matches score >= 0.6; nothing recognizable scores
    below the threshold so the orchestrator clarifies instead of guessing.
    """
    lowered = text.lower()
    words = [w for w in lowered.replace(",", " ").split() if w]
    if not words:
        return "unknown", 0.0
    best_intent, best_hits = "unknown", 0
    for intent, keywords in _INTENT_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in lowered)
        if hits > best_hits:
            best_intent, best_hits = intent, hits
    if best_hits == 0:
        return "unknown", 0.0
    # 1 keyword hit on a short text is decent; 2+ is confident.
    confidence = 0.9 if best_hits >= 2 else 0.65
    # single generic word on a long ramble is weak
    if best_hits == 1 and len(words) > 12:
        confidence = 0.4
    return best_intent, confidence


def route(state: RunState) -> str:
    """'delegate' when confident, 'clarify' when not — never guess."""
    if state.confidence < CONFIDENCE_THRESHOLD:
        return "clarify"
    return "delegate"
