# STATUS.md — Finkow

> Updated: 2026-10-16 (evolution plan complete, local-only). **GitHub
> suspended (403 on all API calls since 2026-10-16 ~00:53 CDT)** — all work
> is local-only until the appeal resolves; no pushes, no PRs. Re-baseline
> against remote on unblock. Local history is linear, one commit per phase,
> ready to become PRs.

## Done

- **v1 (2026-09-26):** virtual-money sandbox (FastAPI + Next.js), verified E2E.
- **v2 (2026-10-06):** provider ports (MarketData/LLM/WebSearch) with AIsa +
  mock + free keyless fallbacks; agent pipeline on append-only event log.
- **v2.1 (2026-10-06):** orchestrator harness (4 specialists, confidence
  routing, checkpoints) + governance (verifier, audit, rate limiter, PII
  filter) + human confirmation gate + Stripe billing skeleton + Alpaca-shaped
  brokerage interface (mock; live path raises).
- **v2.2 (2026-10-06):** agent-money layer — Stripe Checkout credit packs,
  append-only credits ledger, per-call metering, balance + daily/monthly
  caps, HTTP 402 on exhaustion. Full simulated E2E, exact balances.
- **Evolution plan (2026-10-16, all phases complete, local):**
  - **Phase 0** — repository audit + financial-execution reality check
    (baseline: 187 pytest + 36 web tests; tsc 14 errors; build failing).
  - **Phase 1** — source-of-truth docs: `docs/PRODUCT_REFRAME.md`
    authoritative spec (MIT corrected), `docs/PROJECT_BRIEF.md`,
    `docs/VISUAL_DIRECTION.md`, `docs/MCP_SPEC.md`,
    `docs/KEY_SUCCESS.md` (agent-first as hypothesis),
    `design-system/finkow/MASTER.md` → gold system, README rewritten
    honestly, root `AGENTS.md` + `STATUS.md` created.
  - **Phase 4 (financial truth, Roger's order)** — Supabase JWT auth on all
    financial endpoints + account ownership (403); Real/Experimental mode
    separation with contamination tests; SQLite-backed durable store
    (default; audit/event/credits survive restarts) + Supabase skeleton;
    full order lifecycle (draft → awaiting_authorization → submitted →
    filled/rejected/cancelled/failed + partial fills), idempotency keys,
    reconcile-never-assumes-failure; `docs/EXECUTION_PROVIDER.md`
    defines the real-provider contract (no provider chosen — Roger's
    decision, stays OPEN); tests prove mock ≠ real.
  - **Phase 2/3 (visual)** — web build fixed (was red); home is a
    conversational workspace (portfolio indicator with Experimental·virtual
    badge, NL input on the real backend, Activity Inbox with 3 states);
    `/portfolio` view (S16 hierarchy, honest all-time return); opportunity
    cards (discovered/why/evidence/risks/proposed action/next action,
    no-guarantee line); motion made purpose-driven (calm when idle);
    Supabase session Bearer wiring; `NEXT_PUBLIC_FINKOW_API_URL` unified.
  - **Phase 5 (MCP)** — stdio server (`uv run python -m app.mcp.server`,
    official SDK): 12 tools reusing the backend, API-key auth with
    read / read+propose permissions, rate limits, audit logging,
    experimental-only; `prepare_investment_proposal` returns
    pending_authorization; NO execution tools (none exist to expose).
  - **Phase 7 (verification)** — 352 pytest + 60 web tests green; ruff,
    biome, tsc clean; production build green; rendered UI inspected at
    390px + 1440px against the real backend (zero console errors);
    repo-wide outdated-claims sweep clean (no real-money claims, no
    guaranteed returns, no green/IBM-Plex remnants, Elastic mentions
    properly labeled historical).

## Doing

- Nothing — the evolution plan is complete. Awaiting Roger's decisions on
  the blocked items below, then: Supabase wiring end-to-end, Stripe test
  E2E, brokerage selection.

## Next (highest priority, needs Roger)

1. Supabase project + `NEXT_PUBLIC_SUPABASE_URL` /
   `NEXT_PUBLIC_SUPABASE_ANON_KEY` (build-time) + `SUPABASE_JWT_SECRET`
   for the API — unlocks real multi-user auth end-to-end.
2. Brokerage decision (provider, jurisdictions) + credentials + compliance
   review — unlocks the real execution path (interface defined in
   `docs/EXECUTION_PROVIDER.md`).
3. Stripe keys (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`) — unlocks
   billing/credits E2E in test mode.
4. AIsa key top-up (balance was $0.97 on 2026-10-06; rotate keys pasted
   in chat before production).

## Blocked (external)

- GitHub access restoration (blocks the PR workflow entirely; 6 local
  commits ready to become PRs on unblock).
- The four items above (all Roger's).
