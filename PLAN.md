# Finkow — Build Plan

> Spec: `docs/product-context.md`. Stack: Next.js + FastAPI + Supabase + OpenRouter.
> MVP proves: "Can a person develop financial intuition by interacting with a realistic financial sandbox through AI?"

## Confirmed decisions (2026-09-26)

- **Architecture**: Next.js frontend → **FastAPI backend** (financial domain logic) → Supabase (Postgres + Auth)
- **AI**: OpenRouter; AI calls **structured financial operations**, never mutates DB directly
- **Market data**: real data, keyless providers first (e.g. Stooq for stocks, CoinGecko for crypto) behind a provider abstraction; Alpaca paper-trading later
- **Money**: 100% virtual in MVP. Real-money mode is a future phase.
- **Language**: English-first
- **License**: MIT (open source)
- **Brand**: gold `#F59E0B` on deep dark, Swiss-minimalist (see ui-ux-pro-max design system)

## Phase 1 — Sandbox core (MVP)

- [x] Supabase schema: users, sandbox_accounts, positions, transactions, portfolio_snapshots (`supabase/schema.sql`)
- [x] FastAPI: `create_account`, `get_quote(symbol)`, `buy`/`sell` (virtual), `get_portfolio`, `get_history` (`api/`, 30 pytest tests green: 27 domain/API + 3 CORS)
- [x] Market data providers: stocks + crypto, with caching; graceful degradation when offline (Stooq → Yahoo fallback for stocks, CoinGecko for crypto; stale-cache serving; 503 only with nothing cached)
- [x] Next.js: dashboard (portfolio, positions, allocation), asset inspector, buy/sell UI (`web/`; `npm run build` + `npx biome check src` + 10 TS unit tests green). Browser calls the API directly → CORS middleware added on the backend (default `localhost:3000`/`127.0.0.1:3000`, overridable via `FINKOW_CORS_ORIGINS`).
- [x] Virtual cash: $100,000 on signup; transaction ledger; portfolio valuation over time
- [x] Tests: financial math (P&L, allocation, returns) — pytest, no float-money bugs (Decimal everywhere)
- [x] AI skeleton: `POST /api/ai/explain` grounded stub (deterministic summary from real portfolio; OpenRouter rephrase optional via `OPENROUTER_API_KEY`). Full conversational interface is Phase 2.

> **CI note:** `.github/workflows/` files cannot be pushed via the API (stored token
> lacks the `workflows` scope). Add `ci.yml` (pytest + ruff + next build + biome)
> from a local `git push` with a full-scope token — do not attempt via `push_repo.py`.

## Phase 2 — AI interface

- [ ] OpenRouter chat wired to structured ops (get_portfolio, get_quote, simulate, explain)
- [ ] "What happened?" — AI explains portfolio changes from real market movement
- [ ] "What if I invest X?" — simulation without executing
- [ ] Contextual teaching: concepts explained from the user's own actions

## Phase 3 — Opportunities + scenarios (post-MVP)

- [ ] Opportunity scanner (rules first, AI explanation)
- [ ] Scenario engine: crash, inflation, boom, rate shock…

## Explicitly NOT in MVP

Real-money accounts, real execution, compliance infra, every instrument/exchange,
curriculum-style lessons, advertising.

## Open questions (for Roger)

- [x] Product name spelling: **Finkow** — resolved 2026-09-26. Repo renamed `SRogDev/finknow` → `SRogDev/finkow`.
- [x] Confirm MIT license for Finkow? — resolved 2026-09-26: MIT is a confirmed
  decision above and `LICENSE` (MIT) is committed.
