"""Orchestrator: single entry point for the 4-agent harness.

Adapted from Polygrow's ``ai_mind`` graph
(entry -> context_gatherer -> intent_router -> planner -> executor ->
response_formatter -> memory_write, with human_interrupt), as plain-Python
stages — LangGraph would be ceremony at this scale.

Stages:
  entry -> context_gather -> intent_classify -> route ->
    clarify | delegate -> verify -> synthesize -> memory_write -> done

- The orchestrator plans the workflow, delegates to specialists, synthesizes,
  and owns the append-only event log.
- Confidence routing (0.6 threshold): unsure -> clarify (human interrupt),
  never guess.
- Money gate: ``invest`` intents PROPOSE via the InvestmentExecutor's
  confirmation gate — the orchestrator never auto-executes trades.
- Every stage checkpoints; stage failures are recorded on the state and
  returned, never raised to the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.agents.analyst import FinancialAnalyst
from app.agents.events import EventLog
from app.agents.executor import InvestmentExecutor
from app.agents.explainer import Explainer
from app.agents.hunter import OpportunityHunter
from app.agents.learning import LearningAgent
from app.governance.audit import AuditLog
from app.governance.verifier import OutputVerifier
from app.harness.router import classify_intent, route
from app.harness.state import RunState
from app.ports import LLMPort, MarketDataPort, WebSearchPort
from app.store import InMemoryStore

_STAGES = (
    "entry",
    "context_gather",
    "intent_classify",
    "delegate",
    "verify",
    "synthesize",
    "memory_write",
)


@dataclass(frozen=True)
class RunRequest:
    text: str
    account_id: str | None = None


@dataclass(frozen=True)
class RunResult:
    run_id: str
    intent: str
    confidence: float
    requires_human: bool
    human_question: str | None
    results: dict
    checkpoints: list[dict] = field(default_factory=list)
    error: str | None = None


class Orchestrator:
    """Plans, delegates, synthesizes. Owns the event log."""

    def __init__(
        self,
        *,
        store: InMemoryStore,
        market: MarketDataPort,
        llm: LLMPort,
        search: WebSearchPort,
        events: EventLog | None = None,
        audit: AuditLog | None = None,
        verifier: OutputVerifier | None = None,
    ) -> None:
        self._store = store
        self._market = market
        self._llm = llm
        self._search = search
        self._events = events or EventLog()
        self._audit = audit or AuditLog()
        self._verifier = verifier or OutputVerifier()
        self._learning = LearningAgent(llm, store, self._events)
        self._hunter = OpportunityHunter(market, llm, self._events)
        self._analyst = FinancialAnalyst(market, llm, self._events)
        self._executor = InvestmentExecutor(store, market, self._events, self._audit)
        self._explainer = Explainer(store, market, llm, search, self._events)

    # ------------------------------------------------------------ public

    async def run(self, request: RunRequest) -> RunResult:
        state = RunState(
            intent="unknown",
            account_id=request.account_id,
            text=request.text,
        )
        self._events.append(
            "orchestrator", "orchestrator.run_started", {"text": request.text[:200]}
        )
        try:
            await self._stage(state, "entry", self._entry)
            await self._stage(state, "context_gather", self._context_gather)
            await self._stage(state, "intent_classify", self._intent_classify)
            if route(state) == "clarify":
                state.requires_human = True
                state.human_question = (
                    "I want to help with the right thing — did you want to "
                    "invest toward a goal, hunt for opportunities, analyze a "
                    "holding, understand your portfolio, or learn a concept?"
                )
                self._events.append(
                    "orchestrator",
                    "orchestrator.clarification_requested",
                    {"intent": state.intent, "confidence": state.confidence},
                )
                return self._finish(state)
            await self._stage(state, "delegate", self._delegate)
            await self._stage(state, "verify", self._verify)
            await self._stage(state, "synthesize", self._synthesize)
            await self._stage(state, "memory_write", self._memory_write)
        except Exception as exc:  # stage failure: record, never raise
            state.error = f"{type(exc).__name__}: {exc}"
            self._events.append(
                "orchestrator",
                "orchestrator.stage_failed",
                {"stage": state.stages[-1] if state.stages else "?", "error": state.error},
            )
        return self._finish(state)

    # ------------------------------------------------------------ stages

    async def _stage(self, state: RunState, name: str, fn) -> None:
        state.stages.append(name)
        await fn(state)
        state.checkpoints.append(
            {
                "stage": name,
                "at": datetime.now(UTC).isoformat(),
                "intent": state.intent,
            }
        )

    async def _entry(self, state: RunState) -> None:
        if not state.text.strip():
            raise ValueError("empty request text")

    async def _context_gather(self, state: RunState) -> None:
        if state.account_id is not None:
            account = self._store.get_account(state.account_id)
            if account is None:
                raise ValueError(f"account not found: {state.account_id}")
            profile = self._learning.get_profile(state.account_id)
            state.results["profile"] = {
                "risk": profile.risk,
                "horizon_years": profile.horizon_years,
            }

    async def _intent_classify(self, state: RunState) -> None:
        intent, confidence = classify_intent(state.text)
        state.intent, state.confidence = intent, confidence

    async def _delegate(self, state: RunState) -> None:
        if state.intent == "invest":
            await self._delegate_invest(state)
        elif state.intent == "opportunities":
            opportunities = await self._hunter.scan(
                ["AAPL", "MSFT", "NVDA", "VTI", "BND", "BTC", "ETH", "SOL"]
            )
            state.results["opportunities"] = [
                {
                    "symbol": o.symbol,
                    "score": o.score,
                    "price": str(o.price),
                    "reasoning": o.reasoning,
                }
                for o in opportunities
            ]
        elif state.intent == "analyze":
            symbol = self._extract_symbol(state.text)
            analysis = await self._analyst.analyze(symbol)
            state.results["analysis"] = {
                "symbol": analysis.symbol,
                "price": str(analysis.price),
                "verdict": analysis.verdict,
                "risk_flags": analysis.risk_flags,
                "summary_plain": analysis.summary_plain,
            }
        elif state.intent == "explain":
            if state.account_id is None:
                raise ValueError("explain needs an account_id")
            out = await self._explainer.explain(state.account_id, state.text)
            state.results["answer"] = out["answer"]
        elif state.intent == "learn":
            lesson = await self._learning.teach(state.text)
            state.results["lesson"] = lesson
        else:
            raise ValueError(f"no delegate for intent: {state.intent}")

    async def _delegate_invest(self, state: RunState) -> None:
        """Invest intents propose — the human confirmation gate decides."""
        if state.account_id is None:
            raise ValueError("invest needs an account_id")
        plan = await self._learning.plan_goal(state.text, state.account_id)
        self._store.save_plan(f"run:{state.run_id}", _plan_to_dict(plan))
        approval = await self._executor.propose(state.account_id, plan.allocations)
        state.requires_human = True
        state.human_question = (
            f"Approve {len(approval.trades)} paper trades totaling "
            f"${approval.total_usd}? (approval {approval.id})"
        )
        state.results["plan"] = _plan_to_dict(plan)
        state.results["approval_id"] = approval.id
        state.results["proposed_trades"] = approval.trades

    async def _verify(self, state: RunState) -> None:
        payload = {
            k: v for k, v in state.results.items() if k != "profile"
        }
        text = " ".join(
            str(v) for v in payload.values() if isinstance(v, str)
        )
        check = self._verifier.verify(
            {"intent": state.intent, "summary": text[:2000] or state.intent},
            required={"intent": str, "summary": str},
        )
        state.results["verified"] = check.passed
        if not check.passed:
            raise ValueError(f"output verification failed: {check.errors}")

    async def _synthesize(self, state: RunState) -> None:
        parts: list[str] = []
        if state.intent == "opportunities":
            n = len(state.results.get("opportunities", []))
            parts.append(f"I found {n} opportunities worth a look.")
        elif state.intent == "invest":
            parts.append(
                "I built a plan and prepared the trades — nothing moves "
                "until you approve."
            )
        elif state.intent == "analyze":
            a = state.results.get("analysis", {})
            parts.append(f"{a.get('symbol')}: {a.get('verdict')}.")
        elif state.intent == "explain":
            parts.append(str(state.results.get("answer", ""))[:500])
        elif state.intent == "learn":
            parts.append(str(state.results.get("lesson", ""))[:500])
        state.results["response_plain"] = " ".join(p for p in parts if p).strip()

    async def _memory_write(self, state: RunState) -> None:
        self._events.append(
            "orchestrator",
            "orchestrator.run_completed",
            {
                "run_id": state.run_id,
                "intent": state.intent,
                "stages": state.stages,
            },
        )
        self._audit.append(
            actor="orchestrator",
            action="run.completed",
            account_id=state.account_id,
            details={"run_id": state.run_id, "intent": state.intent},
        )

    # ------------------------------------------------------------ direct agent access

    async def analyze(self, symbol: str):
        """Run the FinancialAnalyst directly (also used by the analyze route)."""
        return await self._analyst.analyze(symbol)

    # ------------------------------------------------------------ helpers

    def _extract_symbol(self, text: str) -> str:
        for token in text.replace(",", " ").split():
            cleaned = "".join(c for c in token if c.isalpha()).upper()
            if 1 < len(cleaned) <= 5 and cleaned.isalpha():
                return cleaned
        raise ValueError("could not find a symbol to analyze in the request")

    def _finish(self, state: RunState) -> RunResult:
        return RunResult(
            run_id=state.run_id,
            intent=state.intent,
            confidence=state.confidence,
            requires_human=state.requires_human,
            human_question=state.human_question,
            results=state.results,
            checkpoints=state.checkpoints,
            error=state.error,
        )


def _plan_to_dict(plan) -> dict:
    return {
        "summary_plain": plan.summary_plain,
        "horizon_years": plan.horizon_years,
        "risk_level": plan.risk,
        "allocations": [
            {"symbol": a.symbol, "weight": str(a.weight), "rationale": a.rationale}
            for a in plan.allocations
        ],
    }
