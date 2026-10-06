"""GoalPlanner: natural-language goal -> investment plan.

The user writes what they want in plain words ("grow $1,000 over 5 years, low
risk"); the planner returns an allocation plan in plain language. Amount,
horizon, and risk are extracted deterministically; the LLM port shapes the
allocation and the plain-language summary. Allocations are validated (weights
sum to 1) — an incoherent LLM answer is rejected, never papered over.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.agents.events import EventLog
from app.money import to_cash
from app.ports import ChatMessage, LLMPort, ProviderError

TASK_MARKER = "[finkow-task: goal-plan]"

_LOW_WORDS = ("low risk", "conservative", "safe", "cautious", "calm", "careful")
_HIGH_WORDS = ("high risk", "aggressive", "bold", "maximum growth", "yolo")


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


class GoalPlanner:
    """Turns a natural-language goal into a validated allocation plan."""

    def __init__(self, llm: LLMPort, events: EventLog | None = None) -> None:
        self._llm = llm
        self._events = events or EventLog()

    async def plan(self, goal_text: str) -> Plan:
        spec = parse_goal(goal_text)
        self._events.append(
            "planner",
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
        except (ProviderError, json.JSONDecodeError) as exc:
            raise ValueError(f"planner could not build a valid plan: {exc}") from exc
        self._events.append(
            "planner",
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
