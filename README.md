# Finkow

**Open-source AI-native financial learning sandbox.** Learn finance by interacting with a realistic financial world — not by taking courses.

> Explore → Ask → Simulate → Act → Observe → Understand → Learn → Explore again

## What it is

- **Virtual-money sandbox with real market data** (stocks, ETFs, crypto…): buy, sell, build portfolios, watch real markets move your positions.
- **AI as the primary interface**: ask what happened, why it happened, what-if scenarios, opportunity discovery — the AI calls structured financial operations, never touches raw state.
- **Contextual learning**: concepts arrive inside your own activity, not as lessons.

## What it is not

Budgeting, expense tracking, or household finance. This is about **investing, wealth creation, and financial intuition through doing**. AI-operated actions and real-money mode are explicitly post-MVP.

## Status

- **Scaffold (2026-09-26):** vision + `PLAN.md` + full product spec in `docs/product-context.md`. uv-managed Python deps (`pyproject.toml` + `uv.lock`).
- **MVP build in progress** — Next.js web + FastAPI api scaffolds.
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

MVP is still being built — see `PLAN.md` for the phases.

## License

MIT — see [LICENSE](LICENSE).
