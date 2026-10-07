"""LearningAgent: user profile + goal planning + in-context teaching.

Owns the v2 GoalPlanner logic (moved here, not duplicated): natural-language
goal -> validated allocation plan. Additionally learns the user's profile
(risk, horizon, preferences, decision history) and teaches concepts in plain
language. PII is redacted before anything is persisted.

``agent_name`` lets the legacy ``GoalPlanner`` facade keep emitting the exact
v2 event stream ("planner"/"plan.generated") while new callers use "learning".
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from app.agents.events import EventLog
from app.governance.metering import CreditsExhausted
from app.governance.pii_filter import PIIFilter
from app.money import to_cash
from app.ports import ChatMessage, LLMPort, ProviderError
from app.store import InMemoryStore, UserProfile

TASK_MARKER = "[finkow-task: goal-plan]"
TEACH_MARKER = "[finkow-task: teach]"

_LOW_WORDS = ("low risk", "conservative", "safe", "cautious", "calm", "careful")
_HIGH_WORDS = ("high risk", "aggressive", "bold", "maximum growth", "yolo")
_RISK_LEVELS = ("low", "medium", "high")


@dataclass(frozen=True)
class GoalSpec:
    amount: Decimal
    horizon_years: float
    risk: str  # "low" | "medium" | "high"


@dataclass(frozen=True)
class Allocation:
    symbol: str
    weight: Decimal
    rationale: str


@dataclass(frozen=True)
class Plan:
    summary_plain: str
    horizon_years: float
    risk: str
    allocations: list[Allocation]


def parse_goal(text: str) -> GoalSpec:
    """Deterministic extraction of amount / horizon / risk from free text."""
    amount = Decimal("1000")
    m = re.search(r"\$\s*([\d,]+(?:\.\d{1,2})?)", text)
    if m:
        try:
            amount = to_cash(Decimal(m.group(1).replace(",", "")))
        except InvalidOperation:
            pass
    horizon = 5.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*years?", text, re.IGNORECASE)
    if m:
        horizon = float(m.group(1))
    lowered = text.lower()
    if any(w in lowered for w in _LOW_WORDS):
        risk = "low"
    elif any(w in lowered for w in _HIGH_WORDS):
        risk = "high"
    else:
        risk = "medium"
    return GoalSpec(amount=amount, horizon_years=horizon, risk=risk)


def risk_mentioned(text: str) -> bool:
    """True when the goal text itself names a risk level."""
    lowered = text.lower()
    return any(w in lowered for w in _LOW_WORDS + _HIGH_WORDS)


def horizon_mentioned(text: str) -> bool:
    return bool(re.search(r"(\d+(?:\.\d+)?)\s*years?", text, re.IGNORECASE))


_SYSTEM_PROMPT = (
    f"{TASK_MARKER} You are Finkow's goal planner. The user states an investing "
    "goal in plain language. Respond with a JSON object only:\n"
    '{"summary_plain": "<2-3 plain sentences, zero finance jargon, mention the '
    'dollar amount and horizon>", "horizon_years": <number>, "risk_level": '
    '"<low|medium|high>", "allocations": [{"symbol": "<TICKER>", "weight": '
    "<0-1 decimal>, \"rationale\": \"<one plain sentence>\"}]}. Weights must "
    "sum to 1.0. Use only well-known stocks, ETFs, or crypto. This is paper "
    "money; add no disclaimers beyond one plain sentence."
)

_TEACH_SYSTEM = (
    f"{TEACH_MARKER} You teach one investing concept in plain language. "
    "Zero jargon, 3-5 short sentences, relate it to the user's situation "
    "given in CONTEXT. This is paper money; add no disclaimers beyond one "
    "plain sentence."
)


class LearningAgent:
    """Learns the user profile, plans goals, teaches in context."""

    def __init__(
        self,
        llm: LLMPort,
        store: InMemoryStore | None = None,
        events: EventLog | None = None,
        agent_name: str = "learning",
    ) -> None:
        self._llm = llm
        self._store = store
        self._events = events or EventLog()
        self._agent_name = agent_name
        self._pii = PIIFilter()

    # ------------------------------------------------------------ profile

    def get_profile(self, account_id: str) -> UserProfile:
        if self._store is not None:
            profile = self._store.get_profile(account_id)
            if profile is not None:
                return profile
        return UserProfile(account_id=account_id)

    def update_profile(
        self,
        account_id: str,
        *,
        risk: str | None = None,
        horizon_years: float | None = None,
        preferences: dict | None = None,
    ) -> UserProfile:
        if risk is not None and risk not in _RISK_LEVELS:
            raise ValueError(f"risk must be one of {_RISK_LEVELS}, got {risk!r}")
        if horizon_years is not None and horizon_years <= 0:
            raise ValueError("horizon_years must be positive")
        current = self.get_profile(account_id)
        merged_prefs = dict(current.preferences)
        if preferences:
            merged_prefs.update(self._pii.redact_mapping(preferences))
        profile = UserProfile(
            account_id=account_id,
            risk=risk or current.risk,
            horizon_years=horizon_years or current.horizon_years,
            preferences=merged_prefs,
        )
        if self._store is not None:
            self._store.save_profile(profile)
        self._events.append(
            self._agent_name,
            "learning.profile_updated",
            {"account_id": account_id, "risk": profile.risk},
        )
        return profile

    def record_decision(self, account_id: str, decision: dict) -> UserProfile:
        """Append a user decision to the profile history (for future learning)."""
        profile = self.get_profile(account_id)
        history = list(profile.preferences.get("history", []))
        history.append(
            {**self._pii.redact_mapping(decision), "at": datetime.now(UTC).isoformat()}
        )
        return self.update_profile(account_id, preferences={"history": history})

    # ------------------------------------------------------------ planning

    async def plan_goal(self, goal_text: str, account_id: str | None = None) -> Plan:
        """Natural-language goal -> validated allocation plan.

        When an account profile exists and the goal text doesn't name risk or
        horizon explicitly, the profile's values apply.
        """
        spec = parse_goal(goal_text)
        if account_id is not None:
            profile = self.get_profile(account_id)
            risk = spec.risk if risk_mentioned(goal_text) else profile.risk
            horizon = (
                spec.horizon_years
                if horizon_mentioned(goal_text)
                else profile.horizon_years
            )
            spec = GoalSpec(
                amount=spec.amount, horizon_years=horizon, risk=risk
            )
        self._events.append(
            self._agent_name,
            "goal.received",
            {"text": goal_text[:200], "amount": str(spec.amount), "risk": spec.risk},
        )
        user_prompt = (
            f"RISK: {spec.risk}\n"
            f"AMOUNT: {spec.amount}\n"
            f"HORIZON: {spec.horizon_years}\n"
            f"GOAL: {goal_text.strip()[:500]}"
        )
        try:
            raw = await self._llm.complete(
                [ChatMessage(role="user", content=user_prompt)],
                system=_SYSTEM_PROMPT,
                json_mode=True,
            )
            plan = self._validate(json.loads(raw), spec)
        except CreditsExhausted:
            raise
        except (ProviderError, json.JSONDecodeError) as exc:
            raise ValueError(f"planner could not build a valid plan: {exc}") from exc
        self._events.append(
            self._agent_name,
            "plan.generated",
            {
                "risk": plan.risk,
                "symbols": [a.symbol for a in plan.allocations],
                "horizon_years": plan.horizon_years,
            },
        )
        return plan

    def _validate(self, data: dict, spec: GoalSpec) -> Plan:
        try:
            allocations = [
                Allocation(
                    symbol=str(a["symbol"]).upper().strip(),
                    weight=Decimal(str(a["weight"])),
                    rationale=str(a.get("rationale", "")),
                )
                for a in data["allocations"]
            ]
            summary = str(data["summary_plain"])
        except (KeyError, TypeError, InvalidOperation) as exc:
            raise ValueError(f"plan JSON missing required fields: {exc}") from exc
        if not allocations or any(not a.symbol for a in allocations):
            raise ValueError("plan has no usable allocations")
        total = sum(a.weight for a in allocations)
        if abs(total - Decimal("1")) > Decimal("0.01"):
            raise ValueError(f"allocation weights sum to {total}, not 1")
        risk = str(data.get("risk_level", spec.risk)).lower()
        if risk not in ("low", "medium", "high"):
            risk = spec.risk
        return Plan(
            summary_plain=summary,
            horizon_years=float(data.get("horizon_years", spec.horizon_years)),
            risk=risk,
            allocations=allocations,
        )

    # ------------------------------------------------------------ teaching

    async def teach(self, concept: str, context: str = "") -> str:
        """Explain one concept in plain language, related to the user context."""
        try:
            lesson = await self._llm.complete(
                [
                    ChatMessage(
                        role="user",
                        content=(
                            f"CONCEPT: {concept.strip()[:200]}\n"
                            f"CONTEXT: {context.strip()[:500]}"
                        ),
                    )
                ],
                system=_TEACH_SYSTEM,
            )
        except CreditsExhausted:
            raise
        except ProviderError:
            lesson = (
                f"{concept.strip()}: in plain language — spreading money across "
                "different holdings so no single one decides your outcome. "
                "This is paper money."
            )
        self._events.append(
            self._agent_name, "learning.taught", {"concept": concept[:100]}
        )
        return lesson
