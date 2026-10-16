# Finkow — Project Brief

> Snapshot: 2026-10-16 (Phase 1 of the evolution plan, docs source-of-truth).
> Deeper history: `PLAN.md` (build log), `docs/PRODUCT_REFRAME.md`
> (authoritative spec), `docs/KEY_SUCCESS.md` (strategy).

## What it is

Finkow is an AI-native investment platform: one intelligent system the user
talks to in natural language, backed by specialist agents (goal planning,
opportunity research, financial analysis, paper execution) with human
confirmation gates and full audit. Humans get a conversational interface;
authorized external AI agents get the same trusted capabilities via MCP.

## Current state

- **v1 (2026-09-26):** virtual-money sandbox, verified end to end.
- **v2 (2026-10-06):** provider ports (MarketData/LLM/WebSearch) with AIsa +
  mock + free keyless fallbacks, agent pipeline on an append-only event log,
  goal/radar/invest/explain/activity endpoints.
- **v2.1 (2026-10-06):** orchestrator harness (single entry, 4 specialists,
  confidence routing, checkpoints) + governance (output verifier, audit log,
  rate limiter, PII filter) + human confirmation gate for trades + Stripe
  billing skeleton + Alpaca-shaped brokerage interface (mock only).
- **v2.2 (2026-10-06):** agent-money layer — Stripe Checkout credit packs
  ($5/$20/$50), append-only credits ledger, per-call metering from AIsa's
  actual cost header, balance + daily/monthly caps, HTTP 402 on exhaustion.
- **Phase 0 (2026-10-16):** audit + financial-execution reality check:
  **187 pytest + 36 web tests green**; tsc has 14 errors from legacy v1
  components (a later phase fixes the build); paper-only, no auth, in-memory.
- Web (Next.js 16): gold-system conversational UI exists; production build
  currently fails on legacy v1 imports.

## What it is NOT (today)

A broker. There is no real-money execution and no real brokerage
integration; all trading is paper, honestly labeled. The API has no auth;
all financial state is in-memory (lost on restart); Real/Experimental mode
separation is defined but not yet enforced. See `docs/PRODUCT_REFRAME.md`
§"Current capabilities vs intended product" for the honest list.

## Stack

Next.js 16 → FastAPI (`uv`) → AIsa (models, market data, web search) →
Stripe (product billing + agent credits, test mode) → Supabase (pending;
schema exists, adapter not built).

## Working agreements

- All coding through the `gentle-ai` skill (ODD → TDD → RDD); frontend
  through `ui-ux-pro-max` + `vercel-react-best-practices`; Python via `uv`
  only; English code/comments/docs.
- While GitHub is suspended: one local commit per phase, no pushes; PR
  workflow resumes on unblock (one PR = one logical change, squash-merge).
- Financial honesty is non-negotiable: simulated is never presented as real;
  no guaranteed-return language anywhere; the output verifier enforces it.

## Next

Per `~/workspace/finkow-evolution/SPEC.md`: financial correctness (mode
separation, order lifecycle, auth, persistence) → visual experience →
MCP. Brokerage choice and keys are Roger's decisions; the plan only defines
the interface and documents the gap.
