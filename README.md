# Finkow

**Source-available AI-native financial learning sandbox.** Learn finance by interacting with a realistic financial world — not by taking courses.

> Explore → Ask → Simulate → Act → Observe → Understand → Learn → Explore again

## What it is

- **Virtual-money sandbox with real market data** (stocks, ETFs, crypto…): buy, sell, build portfolios, watch real markets move your positions.
- **AI as the primary interface**: ask what happened, why it happened, what-if scenarios, opportunity discovery — the AI calls structured financial operations, never touches raw state.
- **Contextual learning**: concepts arrive inside your own activity, not as lessons.

## What it is not

Budgeting, expense tracking, or household finance. This is about **investing, wealth creation, and financial intuition through doing**. AI-operated actions and real-money mode are explicitly post-MVP.

## Status

- **MVP (2026-09-26):** FastAPI backend + Next.js 16 dashboard — virtual accounts ($100k), buy/sell at live prices (Yahoo/Coingecko), portfolio P&L and allocation. 30 backend tests passing, verified end to end.
- **Honest limits:** data lives in memory until the Supabase schema is connected; the AI is a deterministic stub — the conversational interface is phase 2.
- **Direction (2026-10-06):** Finkow is a **product**, not fully open source. Market data, LLMs, and web search will route through AIsa (aisa.one) behind clean provider interfaces, with direct providers as fallback.
- Brand: gold `#F59E0B`, Swiss-minimalist.

## Stack

Next.js → FastAPI (financial domain logic) → Supabase → OpenRouter

## Structure

```
finkow/
├── web/      # Next.js app
├── api/      # FastAPI financial domain logic (uv-managed)
├── docs/     # product-context.md — the canonical spec
└── supabase/ # SQL schema
```

See `PLAN.md` for the phases.

## License

Elastic License 2.0 — see [LICENSE](LICENSE). Source-available: you may use, copy, modify, and distribute the code, but you may not provide it to third parties as a hosted or managed service.
