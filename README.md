# Finkow

**Source-available AI investing app.** AI agents invest for you, detect opportunities, and explain everything in plain language — no brokerage apps, no finance jargon.

> Tell Finkow your goal → agents research, invest (paper), and keep you posted.

## What it is

- **Investing autopilot**: state a goal in natural language; AI agents build the plan, detect opportunities, and manage a paper portfolio.
- **Opportunity radar**: agents scan markets and the web for opportunities and bring them to you with plain-language reasoning.
- **Sentient UI**: the app feels alive — proactive briefs, conversational portfolio, ambient status. Finance complexity stays hidden.
- **Learn by watching**: every agent action is explained; financial intuition builds itself.

## What it is not (yet)

A broker. No real-money execution in v2 — paper trading only. Real investing comes later with brokerage connections and compliance.

## Status

- **v2 API (2026-10-06):** provider ports (MarketData/LLM/WebSearch) with AIsa + mock + free direct-fallback adapters and TTL quote caching; agent pipeline — GoalPlanner, OpportunityRadar, PortfolioPilot, Explainer — writing to an append-only event log; goal/radar/invest/explain/activity endpoints on the FastAPI backend. 62 backend tests green (30 v1 + 32 v2), verified against mock providers.
- **v1 (2026-09-26):** virtual-money sandbox (FastAPI + Next.js 16), verified end to end. Now the paper-trading engine under the v2 agents.
- **Honest limits:** single-user, in-memory data (Supabase pending); AIsa adapters are implemented against public docs but not yet live-tested (no API key in CI) — mocks are the verified path.
- Brand: gold `#F59E0B`, Swiss-minimalist.

## Stack

Next.js → FastAPI (agents + financial domain) → AIsa (models, market data, web search) → Supabase (pending)

## Structure

```
finkow/
├── web/      # Next.js app (sentient UI)
├── api/      # FastAPI: agents, paper trading, AIsa providers (uv-managed)
├── docs/     # product-context.md (v1 spec), PRODUCT_REFRAME.md (v2 direction)
└── supabase/ # SQL schema (pending connection)
```

## License

Elastic License 2.0 — see [LICENSE](LICENSE). Source-available: you may use, copy, modify, and distribute the code, but you may not provide it to third parties as a hosted or managed service.
