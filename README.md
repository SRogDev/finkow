# Finkow

**Source-available AI investing app.** AI agents invest for you, detect opportunities, and explain everything in plain language — no brokerage apps, no finance jargon.

> Tell Finkow your goal → agents research, invest (paper), and keep you posted.

## What it is

- **Investing autopilot**: state a goal in natural language; AI agents build the plan, detect opportunities, and manage a paper portfolio.
- **Opportunity radar**: agents scan markets and the web for opportunities and bring them to you with plain-language reasoning.
- **Sentient UI**: the app feels alive — proactive briefs, conversational portfolio, ambient status. Finance complexity stays hidden.
- **Learn by watching**: every agent action is explained; financial intuition builds itself.

## What it is not (yet)

A broker. No real-money execution in v2.1 — paper trading only, with the live-trading path intentionally disabled. Stripe is wired for product billing (flagged); the brokerage is an interface with a mock adapter. Real investing comes later with brokerage keys and compliance.

## Status

- **v2.1 API (2026-10-06):** orchestrator harness (single entry, 4 specialists — LearningAgent, OpportunityHunter, FinancialAnalyst, InvestmentExecutor — confidence routing, checkpoints, adapted from Polygrow patterns) + governance (output verifier, audit log, rate limiter, PII filter) + human confirmation gate for trades + Stripe billing skeleton (flagged) + Alpaca-shaped brokerage interface (mock). Full simulated investment flow verified end to end with exact balances. 154 backend tests green.
- **v2 API (2026-10-06):** provider ports (MarketData/LLM/WebSearch) with AIsa + mock + free direct-fallback adapters and TTL quote caching; agent pipeline writing to an append-only event log; goal/radar/invest/explain/activity endpoints on the FastAPI backend.
- **v1 (2026-09-26):** virtual-money sandbox (FastAPI + Next.js 16), verified end to end. Now the paper-trading engine under the agents.
- **Honest limits:** single-user, in-memory data (Supabase pending); AIsa adapters live-verified via CLI ($0.02 market-data call, <$0.01 LLM, ~$0.016 search); no real-money execution exists or is reachable in this build.
- Brand: gold `#F59E0B`, Swiss-minimalist.

## Stack

Next.js → FastAPI (orchestrator + agents + financial domain) → AIsa (models, market data, web search) → Stripe (product billing, flagged) → Supabase (pending)

## Structure

```
finkow/
├── web/      # Next.js app (sentient UI)
├── api/      # FastAPI: harness, agents, governance, billing, brokerage (uv-managed)
├── docs/     # product-context.md (v1 spec), PRODUCT_REFRAME.md (v2), BUILD_V2_1.md
└── supabase/ # SQL schema (pending connection)
```

## License

Elastic License 2.0 — see [LICENSE](LICENSE). Source-available: you may use, copy, modify, and distribute the code, but you may not provide it to third parties as a hosted or managed service.
