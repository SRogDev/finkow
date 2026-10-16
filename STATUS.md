# STATUS.md — Finkow

> Updated: 2026-10-16. **GitHub suspended (403 on all API calls since
> 2026-10-16 ~00:53 CDT)** — all work is local-only until the appeal
> resolves; no pushes, no PRs. Re-baseline against remote on unblock.

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
- **Phase 0 (2026-10-16):** repository audit + financial-execution reality
  check. Baseline: 187 pytest + 36 web tests green; ruff + biome clean; tsc
  has 14 errors from legacy v1 components; web production build fails (same
  cause). Reality: paper-only, in-memory state, unauthenticated API, no mode
  separation, no MCP. See `PLAN.md` §Phase 0 baseline.
- **Phase 1 (2026-10-16, this phase):** source-of-truth docs —
  `docs/PRODUCT_REFRAME.md` rewritten as authoritative spec (MIT license
  corrected; Elastic claim removed), `docs/product-context.md` labeled v1
  historical archive, `docs/PROJECT_BRIEF.md` created, `docs/VISUAL_DIRECTION.md`
  created, `design-system/finkow/MASTER.md` rewritten to the gold system
  (green CTA / IBM Plex / dashboard patterns removed), `docs/MCP_SPEC.md`
  created (intended, explicitly not implemented), `docs/KEY_SUCCESS.md`
  created (agent-first as hypothesis), README rewritten honestly (MIT, 187
  tests, paper-only limits), `api/README.md` test count fixed (187), root
  `AGENTS.md` + this `STATUS.md` created.

## Doing

- The Finkow evolution plan (`~/workspace/finkow-evolution/SPEC.md`) —
  currently Phase 1 (docs). Next per Roger's order: financial truth
  (mode separation, order lifecycle, auth, persistence) → visual
  experience → MCP.

## Next (highest priority)

1. Fix web build: legacy v1 components vs gold UI; unblock `tsc` + `next build`.
2. Enforce Real/Experimental mode separation in the domain (+ tests proving
   simulated ops cannot contaminate real state).
3. Order lifecycle: explicit states, idempotency keys, timeout reconciliation.
4. API auth: verify Supabase JWTs; enforce user→account ownership.
5. Persist audit/event/credits logs (currently lost on restart).

## Blocked (external)

- GitHub access restoration (blocks the PR workflow entirely).
- Brokerage decision + credentials + compliance review (Roger's; blocks any
  real execution path).
- Supabase project + keys; Stripe keys; AIsa key top-up (Roger's).
