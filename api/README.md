# Finkow API

FastAPI backend for Finkow v2.1 — an orchestrated AI investing harness on
virtual money. Paper trading only; there is no real-money code path.

## Layout

```
api/
  app/
    main.py         # routes: v1 + v2 + v2.1 (harness, gate, audit, billing,
                    #   brokerage, profiles)
    ports.py        # provider ports: MarketDataPort, LLMPort, WebSearchPort
    providers/
      __init__.py   # env-based wiring (AISA_API_KEY -> AIsa, else mocks)
      aisa.py       # AIsa gateway: market data, OpenAI-compatible LLM, Tavily search
      mock.py       # deterministic mocks, provider name "mock"
      direct.py     # free keyless quote fallback (v1 CoinGecko/Stooq/Yahoo chain)
      cached.py     # TTL quote cache + primary/fallback chaining
    harness/
      orchestrator.py  # single entry: entry -> context -> intent -> delegate ->
                       #   verify -> synthesize -> memory_write; checkpoints;
                       #   invest intents PROPOSE, never auto-execute
      router.py        # intent classification + 0.6 confidence routing
      state.py         # RunState
    agents/
      events.py     # append-only agent activity log
      learning.py   # LearningAgent: user profile + goal planning + teaching
      hunter.py     # OpportunityHunter: markets+web scan -> ranked opportunities
      analyst.py    # FinancialAnalyst: fundamentals, valuation sanity, risk
      executor.py   # InvestmentExecutor: paper trades + limits + audit +
                    #   human confirmation gate (propose/confirm). Live path disabled.
      explainer.py  # grounded "what happened / why" answers
      planner.py    # v2 compat facade -> LearningAgent (same event stream)
      radar.py      # v2 compat facade -> OpportunityHunter (same event stream)
      pilot.py      # v2 compat facade -> InvestmentExecutor (same event stream)
    governance/
      verifier.py   # schema + safety checks (PII, guaranteed-returns language)
      audit.py      # append-only audit log for money-affecting actions
      rate_limiter.py  # paid-call budget for AIsa ports (+ wrap_port helper)
      metering.py   # v2.2: MeteredPort + SpendingGovernor — agents spend
                    #   credits on paid AIsa calls, capped before each call
      pii_filter.py # detect + redact PII in stored user text
    billing/
      stripe_billing.py  # Stripe Checkout + webhooks, behind STRIPE_SECRET_KEY.
                         # Product money only — never market orders.
      credits.py    # v2.2: append-only credits ledger (purchases + debits),
                    #   credit packs, micros<->credits conversion
    brokerage.py    # BrokeragePort (Alpaca-shaped) + MockBrokerage.
                    # submit_live_order always raises: live trading disabled.
    trading.py      # paper buy/sell — shared by v1 orders and the executor
    market.py       # v1 provider abstraction (Stooq, CoinGecko, Yahoo) + TTL cache
    portfolio.py    # valuation, P&L, allocation, returns — Decimal-exact
    store.py        # domain records + Store protocol (in-memory; goals, plans,
                    #   profiles, approvals)
    ai.py           # v1 grounded explain stub (OpenRouter polish optional)
    money.py        # Decimal helpers — no float money, ever
  tests/            # pytest: governance, brokerage, billing, agents, harness,
                    #   v2.1 E2E walkthrough, v1+v2 suites
```

Adapted from Polygrow's harness patterns (orchestrator graph, governance
layer, capability registry ideas) — reimplemented light, plain-Python, no
LangGraph: the stages are the same shape, the machinery fits this codebase.

## Run

```bash
uv venv && uv sync                      # creates .venv, installs deps + dev tools
uv run pytest                           # full suite (154 tests)
uv run ruff check app tests             # lint
uv run uvicorn app.main:app --reload --port 8000
```

With `AISA_API_KEY` set, the API uses the AIsa gateway for market data, LLMs,
and web search (with the free direct chain as quote fallback). Paid ports are
rate-limited (`FINKOW_AISA_RATE_LIMIT_PER_MIN`, default 60). Without a key,
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

## Money rails (v2.1)

- **Paper trading is real here**: the executor moves virtual money with exact
  Decimal math, per-trade and daily limits, and a full audit trail. The human
  confirmation gate (`POST /api/executor/propose` -> `POST /api/executor/confirm`)
  is the only way trades happen through the harness — approvals expire after
  15 minutes.
- **Stripe is product billing only**: `POST /api/billing/checkout` creates
  Checkout Sessions and `POST /api/billing/webhook` verifies webhooks, both
  behind `STRIPE_SECRET_KEY` (503 when unset). Stripe moves subscription
  money, never market orders — it is not a brokerage.
- **Brokerage is an interface**: `BrokeragePort` is shaped like Alpaca's
  paper-trading API; `MockBrokerage` simulates fills. `submit_live_order`
  always raises `LiveTradingDisabledError`. Live keys are a later step with
  regulatory review — not this release.

## Agent money: credits (v2.2)

Users buy API credits with their card; agents spend them on paid AIsa calls.
1 credit = $0.001.

- **Buy**: `POST /api/billing/credits/checkout` creates a Stripe Checkout
  Session for a credit pack ($5 -> 5,000 / $20 -> 20,000 / $50 -> 50,000
  credits). `POST /api/billing/webhook` fulfills `checkout.session.completed`
  into the ledger — idempotent per Stripe session id, so replays never
  double-credit. `GET /api/billing/credits/packs` lists packs;
  `GET /api/billing/credits/balance?account_id=…` shows the balance.
  Behind `STRIPE_SECRET_KEY` (503 when unset); subscription billing is
  untouched.
- **Ledger** (`app/billing/credits.py`): append-only `purchase`/`debit`
  entries; balance is always derived, never stored.
- **Metering** (`app/governance/metering.py`): paid AIsa ports are wrapped in
  `MeteredPort` — inside the quote cache and the market fallback chain, so
  cached quotes and free fallbacks are never billed. After each call the
  ACTUAL cost comes from AIsa's `x-aisa-customer-cost-micros-usd` header
  (estimate when the header is absent); mocks and the direct fallback report
  $0 and are never debited. The billed account is bound per request.
- **Spending governor**: balance plus daily/monthly caps
  (`FINKOW_DAILY_CAP_CREDITS` default 1000 = $1/day,
  `FINKOW_MONTHLY_CAP_CREDITS` default 10000 = $10/month; 0 disables), checked
  BEFORE the provider call against a cost estimate. Optional per-call
  `max_price_usd` on the metered port. When a call would exceed balance or a
  cap, AIsa is never called: market data falls back to free direct quotes,
  while LLM/search failures surface as **HTTP 402** with a top-up link —
  agents never silently overspend. `CreditsExhausted` is a `ProviderError`, so
  existing fallback and retry behavior keeps working.
- **Audit**: every debit is a ledger entry (tool, micro-USD, timestamp); each
  orchestrator run writes a `credits.run_summary` entry and purchases write
  `credits.purchase`.

## Design notes

- **Money is exact**: `Decimal` everywhere, quantized at boundaries (`money.py`).
- **Ports, not providers**: agents program against `MarketDataPort`/`LLMPort`/
  `WebSearchPort`/`BrokeragePort`. AIsa, mock, and direct adapters are
  interchangeable; quotes are TTL-cached regardless of provider.
- **Orchestrated, not chained**: one orchestrator plans, delegates to 4
  specialists, verifies outputs, and synthesizes. Confidence < 0.6 ->
  clarification, never a guess. Checkpoints after every stage; failures are
  recorded on the run, not raised.
- **Governance by default**: verifier on agent outputs (schema + safety,
  including a ban on guaranteed-returns language), audit log on every
  money-affecting action, PII redaction on stored user text.
- **Event log**: each agent step appends to an in-memory append-only log,
  readable at `GET /api/agents/activity`.
- **Storage**: `InMemoryStore` implements the `Store` protocol;
  `supabase/schema.sql` is the Postgres target. Domain code never touches storage
  details — swap the adapter later.

## Honest limits

- Single-user, in-memory state (restart wipes it). Supabase is pending.
- Mock providers are deterministic demo data until `AISA_API_KEY` is set.
- No real-money execution exists or is reachable in this build.
- Investing involves risk; the app gives no guaranteed returns (the verifier
  rejects that language outright).

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
| POST | `/api/goals` | create a goal + funded virtual account (PII-redacted) |
| GET | `/api/goals/{id}` | goal details |
| GET | `/api/goals/{id}/plan` | agent-generated allocation plan (plain language) |
| GET | `/api/radar/opportunities` | ranked opportunities with reasoning (`?symbols=` or `?goal_id=`) |
| POST | `/api/portfolio/invest` | paper invest/rebalance by target weights |
| GET | `/api/goals/{id}/portfolio` | goal account portfolio |
| POST | `/api/explain` | v2 grounded explainer (portfolio facts + fresh headlines) |
| GET | `/api/agents/activity` | append-only agent event log |
| POST | `/api/harness/run` | orchestrated run: `{"text": "...", "account_id": "?"}` |
| GET | `/api/analyze/{symbol}` | FinancialAnalyst verdict (fundamentals, valuation, risk) |
| POST | `/api/executor/propose` | dry-run trades -> pending approval (nothing moves) |
| POST | `/api/executor/confirm` | approve/reject a pending approval |
| GET | `/api/audit` | audit log (`?account_id=`, `?action=`) |
| POST | `/api/billing/checkout` | Stripe Checkout Session (503 unless configured) |
| POST | `/api/billing/webhook` | Stripe webhook verification + credits fulfillment |
| POST | `/api/billing/credits/checkout` | credit pack Checkout Session (503 unless configured) |
| GET | `/api/billing/credits/packs` | credit pack catalog |
| GET | `/api/billing/credits/balance?account_id=…` | credits balance |
| GET | `/api/brokerage/account` | mock brokerage account (paper) |
| POST | `/api/brokerage/orders` | mock market order (fills immediately) |
| GET | `/api/brokerage/orders/{id}` | mock order lookup |
| GET | `/api/profile/{id}` | learning profile for an account |
| PUT | `/api/profile/{id}` | update risk / horizon / preferences (PII-redacted) |
