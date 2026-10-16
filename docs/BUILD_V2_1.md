# Finkow v2.1 Build Brief — 2026-10-06 (Roger's directive)

This extends `docs/PRODUCT_REFRAME.md`. Goal: production-ready MVP that feels
like a gold mine, runs a robust agent harness, and is ready for real money
rails (paper/simulated verified now; live money behind explicit keys + gates).

## 1. Design — gold system design (web/)

- **Palette**: deep charcoal/near-black backgrounds (`#0A0A0B`), primary gold
  `#F59E0B`, rich gold gradients (`#FFE9A8 → #F59E0B → #B45309`) for hero
  moments, CTAs, and the portfolio pulse. Premium "gold mine" feel: wealth,
  solidity, calm — never flashy casino.
- **Aceternity UI elements, adapted in-repo** (Tailwind + motion, product's own
  voice): spotlight cards for opportunities, background beams / tracing beam
  for the agent activity feed, infinite-moving-cards for the opportunity rail,
  lamp/hero glow on the goal screen. Implement as local components; do not
  depend on the aceternity package if it complicates the build.
- **Sentient UI + bespoke UI principles**: every surface feels alive and
  crafted — proactive briefs, conversational portfolio, ambient status,
  plain-language explanations, calm. No generic fintech look. Run
  ui-ux-pro-max design-system lookup first.

## 2. API — agent harness v2.1 (adapt Polygrow patterns, don't blind-copy)

Reference (read on GitHub SRogDev/Polygrow, `ai-services/src/ai_services/app/`):
- `ai_mind/graph.py|state.py|router.py` — LangGraph orchestrator: entry →
  context_gatherer → intent_router → planner → executor → response_formatter →
  memory_write → END; conditional routing on intent+confidence; human_interrupt.
- `governance_layer/` — verifier (schema + safety checks), audit logger (every
  action: user/model/tokens/cost/duration/nodes/outcome), rate_limiter,
  pii_filter.
- `capability_engine/` — registry + executor + `aisa_bridge.py`.
- `control_loop/` — loop with checkpoint + error_handler.

Adapt to Finkow's codebase (keep it light — plain-Python stages are fine;
LangGraph only if clearly justified):

- **Orchestrator** (single entry point): plans the workflow for a user intent,
  delegates to specialists, synthesizes, owns the append-only event log.
  Confidence-threshold routing like Polygrow's router.
- **4 specialist agents (Roger's names)**:
  - `LearningAgent` — learns the user's profile (risk, horizon, preferences,
    decision history) and teaches concepts in context.
  - `OpportunityHunter` — scans markets + web (AIsa) → ranked opportunities
    with plain-language reasoning.
  - `FinancialAnalyst` — fundamentals, filings, valuation sanity checks, risk
    analysis.
  - `InvestmentExecutor` — executes paper trades now; owns limits, audit
    trail, and the **human confirmation gate** (adapted from Polygrow's
    `human_interrupt`): any real-money move requires explicit user approval.
    NO live-trading code path is enabled in v2.1.
- **Governance (adapted)**: output verifier (schema + safety) on agent
  outputs; audit log for every money-affecting action; rate limits on
  paid AIsa calls; PII filter on stored user text.
- This refactors (not duplicates) the v2 planner/radar/pilot/explainer —
  rename/restructure into the orchestrator + 4 agents.

## 3. Money rails (flagged, safe — paper/simulated verified)

- **Stripe (Roger's explicit choice for Finkow billing)**: product billing only
  (subscriptions / one-time) — Checkout Sessions + webhook handler skeleton,
  everything behind `STRIPE_SECRET_KEY` presence; tests use mocks; no live
  calls. Document clearly: **Stripe moves product money, never market orders**
  — it is not a brokerage.
- **Brokerage interface only**: `BrokeragePort` shaped like Alpaca's
  paper-trading API; mock adapter for simulation. Live keys are Roger's later
  step. Compliance note in README: real investing needs brokerage + local
  regulations; the app gives no guaranteed returns.
- Real-money execution stays **disabled**; the human confirmation gate is the
  only path that could ever enable it, and only with keys + explicit user opt-in.

## 4. Verification — do not stop until green (simulated)

Full simulated investment flow, end to end, asserting exact balances at each
step (no real money): fund paper account → set goal → plan → hunt
opportunities → analyze → execute (paper) → portfolio + explanation + audit
log. pytest green, ruff clean; web tsc + production build green.

## 5. Deliverables

- PR(s) with evidence (test counts, simulated E2E transcript, SHAs).
- README touch-up (English): v2.1 architecture, money-rails status, honest
  limits.
- STATUS.md updated.
- Final production-readiness checklist (keys, services, compliance) delivered
  to Roger with the report.

## Engineering rules (non-negotiable)

- gentle-ai: ODD → TDD → RDD. uv only for Python.
- PR workflow: branch → PR → squash-merge; never push to `main`.
- Elastic License 2.0. English code/docs.
