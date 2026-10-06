# STATUS — finkow

> Single source of truth for where this project stands. Last updated: 2026-10-06.
> Read this before starting work. Update it in the same PR when reality changes.

## Done
- 2026-09-26 — Repo created (SRogDev/finkow, renamed from finknow per Roger). Scaffold pushed: vision README + PLAN.md.
- 2026-09-26 — Roger's full product spec extracted to `docs/product-context.md`.
- 2026-09-26 — uv-managed Python deps (`uv venv`, `pyproject.toml [project]` + `uv.lock`).
- 2026-09-26 — v1 built and verified: FastAPI backend + Next.js 16 dashboard, virtual accounts ($100k), buy/sell at live Yahoo/Coingecko prices, portfolio P&L and allocation. 30 backend tests passing.
- 2026-10-06 — License changed MIT → Elastic License 2.0: Finkow is a source-available product, not fully open source (Roger's decision).
- 2026-10-06 — v2 product reframe: AI investing product that democratizes finance (brief in `docs/PRODUCT_REFRAME.md`).
- 2026-10-06 — v2 web merged (PR #5): sentient UI conversational home.
- 2026-10-06 — v2 API merged (PR #6): provider ports + AIsa adapters + 4-agent pipeline, 62 tests.
- 2026-10-06 — AIsa connected + live-verified (market data $0.02/call, LLM <$0.01, search ~$0.016).
- 2026-10-06 — v2.1 API merged: orchestrator + 4 specialists (LearningAgent, OpportunityHunter, FinancialAnalyst, InvestmentExecutor) + governance (verifier, audit, rate limiter, PII filter) + human confirmation gate + Stripe billing skeleton (flagged) + Alpaca-shaped brokerage interface (mock). Simulated E2E investment flow verified with exact balances. 154 tests green.

## In progress / blocked
- v2.1 web (gold system design, Aceternity-style sentient UI) — separate track.

## Next
- Screenshot + production-readiness checklist for Roger.
- Connect Supabase schema (data currently in-memory).
- Real-money execution (phase 3): brokerage keys + compliance — explicitly out of v2.1 scope (interface only, disabled path).
- Per PLAN.md phases; brand gold #F59E0B.
