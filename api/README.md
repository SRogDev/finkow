# Finkow API

FastAPI backend for Finkow v2 — AI investing agents on virtual money.
Paper trading only; there is no real-money code path.

## Layout

```
api/
  app/
    main.py         # routes: v1 (accounts, quotes, orders, portfolio, history,
                    #   ai/explain) + v2 (goals, radar, invest, explain, activity)
    ports.py        # provider ports: MarketDataPort, LLMPort, WebSearchPort
    providers/
      __init__.py   # env-based wiring (AISA_API_KEY -> AIsa, else mocks)
      aisa.py       # AIsa gateway: market data, OpenAI-compatible LLM, Tavily search
      mock.py       # deterministic mocks, provider name "mock"
      direct.py     # free keyless quote fallback (v1 CoinGecko/Stooq/Yahoo chain)
      cached.py     # TTL quote cache + primary/fallback chaining
    agents/
      events.py     # append-only agent activity log
      planner.py    # natural-language goal -> allocation plan
      radar.py      # market data + news -> ranked opportunities with reasoning
      pilot.py      # paper-trade execution + rebalancing on v1 accounts
      explainer.py  # grounded "what happened / why" answers
    trading.py      # paper buy/sell — shared by the v1 order endpoint and the pilot
    market.py       # v1 provider abstraction (Stooq, CoinGecko, Yahoo) + TTL cache
    portfolio.py    # valuation, P&L, allocation, returns — Decimal-exact
    store.py        # domain records + Store protocol (in-memory impl; goals/plans too)
    ai.py           # v1 grounded explain stub (OpenRouter polish optional)
    money.py        # Decimal helpers — no float money, ever
  tests/            # pytest: ports, agents, v2 API walkthrough, v1 suite
```

## Run

```bash
uv venv && uv sync                      # creates .venv, installs deps + dev tools
uv run pytest                           # full suite (v1 + v2)
uv run ruff check app tests             # lint
uv run uvicorn app.main:app --reload --port 8000
```

With `AISA_API_KEY` set, the API uses the AIsa gateway for market data, LLMs,
and web search (with the free direct chain as quote fallback). Without it,
deterministic mock providers are used — every market fact is still read
through the port, and mock data is clearly labeled.

```bash
AISA_API_KEY=... FINKOW_QUOTE_TTL_SECONDS=60 .venv/bin/uvicorn app.main:app --port 8000
```

The frontend calls the API directly from the browser, so the server emits
CORS headers. Defaults allow `http://localhost:3000` and
`http://127.0.0.1:3000`; override in production with a comma-separated list:

```bash
FINKOW_CORS_ORIGINS=https://finkow.example.com .venv/bin/uvicorn app.main:app --port 8000
```

## Design notes

- **Money is exact**: `Decimal` everywhere, quantized at boundaries (`money.py`).
- **Ports, not providers**: agents program against `MarketDataPort`/`LLMPort`/
  `WebSearchPort`. AIsa, mock, and direct adapters are interchangeable;
  quotes are TTL-cached regardless of provider.
- **Grounded agents**: every market fact flows through the MarketData port, every
  AI sentence through the LLM port. Numbers are computed from real data first;
  the LLM only shapes them into plain language.
- **Event log**: each agent step appends to an in-memory append-only log,
  readable at `GET /api/agents/activity`.
- **Storage**: `InMemoryStore` implements the `Store` protocol;
  `supabase/schema.sql` is the Postgres target. Domain code never touches storage
  details — swap the adapter later.

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | liveness |
| POST | `/api/accounts` | create sandbox account ($100,000 virtual) |
| GET | `/api/quotes/{symbol}` | live quote (`AAPL`, `BTC`, …) |
| POST | `/api/orders` | virtual buy/sell |
| GET | `/api/accounts/{id}/portfolio` | valuation, P&L, allocation |
| GET | `/api/accounts/{id}/transactions` | ledger |
| GET | `/api/accounts/{id}/history` | portfolio snapshots |
| POST | `/api/ai/explain` | v1 grounded "what happened to my portfolio?" |
| POST | `/api/goals` | create a goal (`{"text": "grow $1,000 over 5 years, low risk"}`) + funded virtual account |
| GET | `/api/goals/{id}` | goal details |
| GET | `/api/goals/{id}/plan` | agent-generated allocation plan (plain language) |
| GET | `/api/radar/opportunities` | ranked opportunities with reasoning (`?symbols=` or `?goal_id=`) |
| POST | `/api/portfolio/invest` | paper invest/rebalance by target weights |
| GET | `/api/goals/{id}/portfolio` | goal account portfolio |
| POST | `/api/explain` | v2 grounded explainer (portfolio facts + fresh headlines) |
| GET | `/api/agents/activity` | append-only agent event log |
