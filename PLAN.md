# Finkow — Build Plan

> Contract: `~/workspace/finkow-evolution/SPEC.md` (S13 = this Phase 0 audit).
> Stack: Next.js 16 + FastAPI (`uv`) + Supabase (pending) + AIsa + Stripe.
> Thesis: AI-native investing; paper trading now, real money later with
> brokerage keys + compliance.
> License: **MIT** — the committed `LICENSE` file is MIT (README and
> `docs/PRODUCT_REFRAME.md` claims corrected in Phase 1).

## Phase 0 baseline (2026-10-16)

Local git reconstruction (commit `8ea343e`, "local reconstruction of remote
main a522bee"). GitHub is suspended (403 on all calls) — nothing here is
verifiable against remote; re-baseline on unblock. Read-only audit + test
runs; no commits, no live API calls (no keys on this machine).

| Suite | Command | Result |
|---|---|---|
| API tests | `cd api && uv sync && uv run pytest` | **187 passed, 0 failed** (3.39s) |
| API lint | `cd api && uv run ruff check app tests` | clean |
| Web tests | `cd web && npm install --legacy-peer-deps && npm test` (node:test, zero deps) | **36 passed, 0 failed** |
| Web typecheck | `cd web && npx tsc --noEmit` | **14 errors** (gap 7 below) |
| Web lint | `cd web && npx biome check src` | clean (39 files) |
| Web build | `cd web && npm run build` | **FAILS** (same cause as typecheck) |

## Capability classification (SPEC S13 five states)

| # | Area | State | Evidence |
|---|---|---|---|
| 1 | Portfolio data + persistence | partially implemented | Decimal-exact valuation/P&L/allocation + transactions/snapshots tested; persistence is in-memory only (`InMemoryStore`), Supabase adapter not built |
| 2 | Real vs simulated trading | mocked or simulated | Paper only: `MockBrokerage` fills instantly; `submit_live_order` always raises `LiveTradingDisabledError`; labeled honestly in code/docs |
| 3 | Market data freshness/source | partially implemented | Port chain AIsa → keyless direct (Yahoo/Stooq/CoinGecko) → mock, TTL-cached (default 60s); live freshness unverified (zero live calls in this audit) |
| 4 | Order lifecycle | partially implemented | propose/confirm gate (15-min expiry) + exact paper execution verified; only `filled`/`rejected` statuses — no partial fills, cancel-submitted, timeouts, or reconciliation |
| 5 | Agent orchestration + background tasks | partially implemented | Orchestrator + 4 agents + governance verified request-scoped; no background workers/schedulers (runs only on HTTP request) |
| 6 | Financial permissions + risk controls | partially implemented | $25k/trade cap, daily trade limit, 15-min approval expiry, output verifier, agent-credit daily/monthly caps — all tested; no per-user permissions (API has no auth) |
| 7 | Auth + account isolation | partially implemented | Supabase sign-in gate in web (disabled when unconfigured); FastAPI endpoints have no auth and no user→account ownership checks |
| 8 | Audit logs + execution history | implemented but insufficiently verified | Append-only audit log, agent event log, credits ledger covered by tests; all in-memory — lost on restart, not persisted |
| 9 | API surface for external clients | partially implemented | 31 REST endpoints, tested; no MCP, no API keys, no auth — not ready for external agents |
| 10 | Mobile/desktop experience | partially implemented | v2.1 gold conversational home/components exist; production build fails (legacy v1 imports); UI defaults to mock adapter, never touches the backend without `NEXT_PUBLIC_FINKOW_ADAPTER=http` |

## Implementation checklist

### (a) Doable with current architecture — all done 2026-10-16

- [x] Fix web build: legacy v1 components adapted to gold primitives
  (`/assets/[symbol]` kept working); `tsc` + `next build` green
- [x] Real/Experimental mode separation in the domain (SPEC S8): mode on
  accounts/orders/holdings/transactions/approvals; `CrossModeError`;
  contamination tests both directions; real-mode execution → 501
- [x] Order lifecycle: explicit states (draft/awaiting_authorization/
  submitted/partially_filled/filled/rejected/cancelled/failed), idempotency
  keys, reconcile-never-assumes-failure
- [x] API auth: Supabase JWT verification on FastAPI endpoints; enforce
  user→account ownership (403); per-user daily trade limit
- [x] Audit/event/credits logs persisted (SQLite default via `FINKOW_STORE`;
  survive restarts) + Supabase skeleton adapter
- [x] Resolve LICENSE/docs mismatch: `LICENSE` file is MIT; README and
  `docs/PRODUCT_REFRAME.md` claimed Elastic 2.0 → corrected in Phase 1
- [x] Update `api/README.md` test count (187, not 154)
- [x] Single source of truth docs (SPEC S14): `docs/PRODUCT_REFRAME.md`
  authoritative; align/label `docs/product-context.md` historical; write
  `docs/VISUAL_DIRECTION.md`, `docs/MCP_SPEC.md`, `docs/KEY_SUCCESS.md` —
  done in Phase 1
  `docs/VISUAL_DIRECTION.md`, `docs/MCP_SPEC.md`, `docs/KEY_SUCCESS.md`;
  clean `design-system/finkow/MASTER.md` (remove green `#22C55E` CTA,
  IBM Plex Sans, trading-dashboard patterns); rewrite README honestly
- [x] MCP implementation (SPEC S18) — stdio server, 12 tools reusing the
  backend, API-key auth (read / read+propose), experimental-only, no
  execution tools; `docs/MCP_SPEC.md` rewritten as implemented spec

### (b) Needs a new integration or credentials

- [ ] Supabase project + `NEXT_PUBLIC_SUPABASE_URL` /
  `NEXT_PUBLIC_SUPABASE_ANON_KEY` → build the `Store` adapter, connect auth
  persistence (Roger's Supabase project)
- [ ] Stripe keys (`STRIPE_SECRET_KEY`, webhook secret, price IDs) →
  billing E2E in test mode
- [ ] AIsa API key (top-up) → live market data / LLM / search
- [ ] CI: `.github/workflows/ci.yml` needs a full-scope token
  (stored token lacks `workflows` scope)

### (c) Blocked by external dependencies

- [ ] Real brokerage execution: provider decision is Roger's (SPEC S24 — do
  not invent); then credentials + compliance review; `submit_live_order`
  stays disabled until then
- [ ] GitHub access restoration (403 account suspended) — blocks the PR
  workflow entirely

### (d) Out of scope

- [ ] Choosing a real brokerage provider (Roger's decision, not the implementer's)
- [ ] New database, orchestration framework, brokerage, or visual library
  unless Phase 0 established a concrete reason (SPEC S21)
- [ ] Rebuilding the app from scratch (SPEC S6)
- [ ] Guaranteed-return language anywhere (SPEC S16)
- [ ] Monetization/commercial internals beyond the Stripe test-mode skeleton

---

## Historical (v1, 2026-09-26) — superseded by the Phase 0 audit and the v2 reframe above

> Spec: `docs/product-context.md`. Stack: Next.js + FastAPI + Supabase + OpenRouter.
> MVP proves: "Can a person develop financial intuition by interacting with a realistic financial sandbox through AI?"

### Confirmed decisions (2026-09-26)

- **Architecture**: Next.js frontend → **FastAPI backend** (financial domain logic) → Supabase (Postgres + Auth)
- **AI**: OpenRouter; AI calls **structured financial operations**, never mutates DB directly
- **Market data**: real data, keyless providers first (e.g. Stooq for stocks, CoinGecko for crypto) behind a provider abstraction; Alpaca paper-trading later
- **Money**: 100% virtual in MVP. Real-money mode is a future phase.
- **Language**: English-first
- **License**: MIT (open source)
- **Brand**: gold `#F59E0B` on deep dark, Swiss-minimalist (see ui-ux-pro-max design system)

### Phase 1 — Sandbox core (MVP)

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

### Phase 2 — AI interface

- [ ] OpenRouter chat wired to structured ops (get_portfolio, get_quote, simulate, explain)
- [ ] "What happened?" — AI explains portfolio changes from real market movement
- [ ] "What if I invest X?" — simulation without executing
- [ ] Contextual teaching: concepts explained from the user's own actions

### Phase 3 — Opportunities + scenarios (post-MVP)

- [ ] Opportunity scanner (rules first, AI explanation)
- [ ] Scenario engine: crash, inflation, boom, rate shock…

### Explicitly NOT in MVP

Real-money accounts, real execution, compliance infra, every instrument/exchange,
curriculum-style lessons, advertising.

### Open questions (for Roger)

- [x] Product name spelling: **Finkow** — resolved 2026-09-26. Repo renamed `SRogDev/finknow` → `SRogDev/finkow`.
- [x] Confirm MIT license for Finkow? — resolved 2026-09-26: MIT is a confirmed
  decision above and `LICENSE` (MIT) is committed.
