# Finkow Product Reframe — v2 (2026-10-06)

Owner directive. This document overrides the v1 "learning sandbox" positioning
where it conflicts. `docs/product-context.md` remains the v1 spec archive.

## One-liner

Democratize investing: AI agents that invest for you, detect opportunities, and
explain everything in plain language. No brokerage apps. No finance jargon.
Anyone can grow money.

## What changed

- FROM: open-source financial learning sandbox (user drives, virtual money,
  learning-by-doing).
- TO: source-available (Elastic License 2.0) consumer **product** — autonomous
  AI investing agents. The user states goals in natural language; agents do the
  rest. v2 trades with **paper money only**. Real-money execution is phase 3
  (brokerage connections + compliance) — explicitly out of scope.

## Product principles

1. **Radical simplification.** The user never sees a ticker, order type, or
   brokerage screen unless they ask. One goal in, one portfolio out.
2. **Sentient UI.** The app feels alive: proactive (opportunities and briefs
   arrive unprompted), conversational (natural language first, not forms),
   ambient (the portfolio has a pulse, not a spreadsheet), explanatory (every
   agent action shows its reasoning in plain language), calm (no trading-app
   noise — no candlestick overload, no jargon).
3. **Trust through transparency.** Agents earn trust by showing *why* in plain
   language for every action. No black-box moves.
4. **Abstract the world's finance into one place.** Stocks, ETFs, crypto —
   one portfolio, one language, one app.

## v2 MVP scope

### API (FastAPI, `api/`)

- **Provider ports** (interfaces, dependency-injected):
  - `MarketData`: quotes, fundamentals, news. AIsa implementation via
    `https://api.aisa.one/apis/v1/financial/*` (stocks incl. intraday, crypto,
    filings). Mock adapter when `AISA_API_KEY` is absent. Direct
    Yahoo/Coingecko fallback adapter for quotes (free, no key).
  - `LLM`: chat completions. AIsa implementation via OpenAI-compatible
    `https://api.aisa.one/v1`. Mock adapter (deterministic) when no key.
  - `WebSearch`: AIsa implementation (Tavily). Mock adapter when no key.
- **Agent pipeline** (small orchestrated steps, no heavy framework required;
  each step writes to an append-only event log; all LLM calls go through the
  LLM port with structured prompts; all market facts through the MarketData
  port — no hardcoded numbers):
  - `GoalPlanner`: natural-language goal → investment plan (allocation,
    horizon, risk) in plain language.
  - `OpportunityRadar`: scans market data + web search → ranked opportunities
    with reasoning.
  - `PortfolioPilot`: paper-trade execution + rebalancing (extends the v1
    virtual accounts).
  - `Explainer`: "what happened / why" for portfolio moves and agent actions,
    grounded in real data.
- **Endpoints** (draft): `POST /goals`, `GET /goals/{id}/plan`,
  `GET /radar/opportunities`, `POST /portfolio/invest` (paper),
  `GET /portfolio`, `POST /explain`, `GET /agents/activity` (event log).
- Quote caching: aggressive (TTL) regardless of provider — cost and latency.

### Web (Next.js, `web/`)

- **One conversational home.** Sentient UI per principles above:
  - natural-language goal input ("grow $1,000 over 5 years, low risk"),
  - live agent activity feed ("Radar found 3 opportunities"),
  - portfolio pulse (alive status, plain-language),
  - opportunity cards with one-tap paper invest,
  - explanations everywhere, zero jargon by default.
- Brand: gold `#F59E0B`, Swiss-minimalist. **Run the ui-ux-pro-max
  design-system lookup first** (`scripts/search.py --design-system`), then
  implement. No exceptions.

### Non-goals (v2)

Real-money execution. Multi-user auth/billing. Supabase migration (still
pending Roger — keep in-memory storage, note it).

## Acceptance criteria

1. Goal "grow $1,000 over 5 years, low risk" → plan with allocation, in plain
   language, no jargon.
2. Radar returns ≥ 3 opportunities with reasoning (mock or AIsa).
3. One-tap paper invest → portfolio updates with live (or mock) prices.
4. "Why did my portfolio move today?" → grounded explanation citing real data.
5. Every market fact flows through the MarketData port; every AI text through
   the LLM port.
6. Backend: pytest green. Web: `tsc` clean + production build green.

## Engineering rules (non-negotiable)

- gentle-ai skill: ODD → TDD → RDD. No exceptions.
- PR workflow: branch → PR → squash-merge. Never push to `main` directly.
  (Muse merges his own PRs — Roger authorized.)
- README touch-up in the same PR (English, current, no invented claims).
- Elastic License 2.0. English code, comments, and docs.
