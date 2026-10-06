# STATUS — finkow

> Single source of truth for where this project stands. Last updated: 2026-10-06.
> Read this before starting work. Update it in the same PR when reality changes.

## Done
- 2026-09-26 — Repo created (SRogDev/finkow, renamed from finknow per Roger). Scaffold pushed: vision README + PLAN.md.
- 2026-09-26 — Roger's full product spec extracted to `docs/product-context.md`.
- 2026-09-26 — uv-managed Python deps (`uv venv`, `pyproject.toml [project]` + `uv.lock`).
- 2026-09-26 — v1 built and verified: FastAPI backend + Next.js 16 dashboard, virtual accounts ($100k), buy/sell at live Yahoo/Coingecko prices, portfolio P&L and allocation. 30 backend tests passing.
- 2026-10-06 — License changed MIT → Elastic License 2.0: Finkow is a source-available product, not fully open source (Roger's decision).
- 2026-10-06 — v2 product reframe: Finkow is now an AI investing product that democratizes finance (brief in `docs/PRODUCT_REFRAME.md`).

## In progress / blocked
- v2 build: API (AIsa provider ports + GoalPlanner/Radar/Pilot/Explainer agents + paper trading) and web (simplified sentient UI) — two builders running.

## Next
- Verify + merge v2 builder PRs.
- Connect Supabase schema (data currently in-memory).
- Real-money execution (phase 3): brokerage connections + compliance — explicitly out of v2 scope.
- Per PLAN.md phases; brand gold #F59E0B.
