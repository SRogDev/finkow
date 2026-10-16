# Finkow

**AI-native investment platform.** Tell Finkow your goal in plain language —
one intelligent system researches, plans, manages a portfolio, and explains
every move in plain language.

## What it is

- **Conversational investing**: natural-language goals → agent-built plan,
  opportunity radar, managed paper portfolio, grounded explanations.
- **One intelligent system**: an orchestrator delegates to specialists
  (goal learning, opportunity hunting, financial analysis, execution) — the
  specialists stay internal; the user talks to Finkow.
- **Two modes**: Experimental (virtual/paper capital) and Real
  (real money). Modes never mix state — simulated is never presented as real.
  The Real path is not built yet; the live order path is intentionally disabled.
- **MCP direction**: authorized external AI agents will get the same trusted
  capabilities through MCP — intended, scoped, and gated on API auth + mode
  separation. Not implemented yet (see `docs/MCP_SPEC.md`).

## Implemented capabilities (honest)

- Orchestrator + 4 specialist agents, confidence routing, checkpoints
- Human confirmation gate on trades (approvals expire after 15 minutes)
- Paper trading with Decimal-exact math, per-trade and daily limits
- Goal planning, opportunity radar, grounded explainer, agent activity log
- Governance: output verifier, append-only audit log, rate limiter, PII filter
- Agent-money layer: Stripe Checkout credit packs ($5/$20/$50), append-only
  credits ledger, per-call metering from AIsa's actual cost, balance +
  daily/monthly caps, HTTP 402 on exhaustion
- Market data chain: AIsa → keyless direct (Yahoo/Stooq/CoinGecko) →
  deterministic mock, TTL-cached

## Honest limits

- **Paper only.** No real-money execution exists or is reachable in this build.
- **In-memory.** Restart wipes everything (audit log, event log, credits
  ledger). Supabase is pending.
- **Unauthenticated API.** FastAPI endpoints have no auth; user→account
  ownership is not enforced.
- **187 backend tests + 36 web tests green** (2026-10-16 audit). The web
  production build currently fails on legacy v1 imports (being fixed).

## Status

- **Phase 0 (2026-10-16):** audit + financial-execution reality check (see
  `PLAN.md`). 187 pytest + 36 web tests green; tsc has 14 legacy errors.
- **v2.2 (2026-10-06):** agent-money layer (credits, metering, caps), full
  simulated E2E with exact balances.
- **v2.1 (2026-10-06):** orchestrator harness + governance + confirmation
  gate + Stripe billing skeleton + Alpaca-shaped brokerage interface (mock).
- **v1 (2026-09-26):** virtual-money sandbox (the paper-trading engine under
  the agents).
- Brand: gold `#F59E0B` on dark charcoal — minimalist financial observatory,
  not a trading dashboard.

## Stack

Next.js 16 → FastAPI (`uv`) → AIsa (models, market data, web search) →
Stripe (test mode) → Supabase (pending)

## Structure

```
finkow/
├── web/                  # Next.js app (gold conversational UI)
├── api/                  # FastAPI: harness, agents, governance, billing, brokerage (uv-managed)
├── docs/                 # PRODUCT_REFRAME.md (authoritative spec), MCP_SPEC.md, KEY_SUCCESS.md,
│                         #   VISUAL_DIRECTION.md, PROJECT_BRIEF.md, product-context.md (v1 archive)
├── design-system/finkow/ # MASTER.md (gold design system)
└── supabase/             # SQL schema (pending connection)
```

## Docs

- `docs/PRODUCT_REFRAME.md` — the authoritative product spec
- `docs/KEY_SUCCESS.md` — strategic mission (agent-first as hypothesis)
- `docs/MCP_SPEC.md` — intended external-agent interface (not implemented)
- `docs/VISUAL_DIRECTION.md` — visual brief

## License

MIT — see [LICENSE](LICENSE).
