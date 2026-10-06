# STATUS — finkow

> Single source of truth for where this project stands. Last updated: 2026-10-06.
> Read this before starting work. Update it in the same PR when reality changes.

## Done
- 2026-09-26 — Repo created (SRogDev/finkow, renamed from finknow per Roger). Scaffold pushed: vision README + PLAN.md.
- 2026-09-26 — Roger's full product spec extracted to `docs/product-context.md`.
- 2026-09-26 — uv-managed Python deps (`uv venv`, `pyproject.toml [project]` + `uv.lock`).
- 2026-09-26 — MVP built and verified: FastAPI backend + Next.js 16 dashboard, virtual accounts ($100k), buy/sell at live Yahoo/Coingecko prices, portfolio P&L and allocation. 30 backend tests passing.
- 2026-10-06 — License changed MIT → Elastic License 2.0: Finkow is a source-available product, not fully open source (Roger's decision).

## In progress / blocked
- (none)

## Next
- AIsa provider interfaces (market data, LLM, web search) with direct-provider fallback — per Roger's 2026-10-06 decision.
- Connect Supabase schema (data currently in-memory); conversational AI interface (phase 2, replaces deterministic stub).
- Per PLAN.md phases; brand gold #F59E0B.
