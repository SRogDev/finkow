# Finkow API

FastAPI backend for Finkow v2.1 — an orchestrated AI investing harness on
virtual money. Paper trading only; there is no real-money code path.

## Layout

```
api/
  app/
    main.py         # routes: v1 + v2 + v2.1 (harness, gate, audit, billing,
                    #   brokerage, profiles) + auth/ownership/mode wiring
    auth.py         # Supabase JWT (HS256) verification, require_user,
                    #   require_account_owner; dev-mode graceful degradation
    modes.py        # Mode enum (real/experimental), cross-mode invariant
    storage_sqlite.py  # durable SQLite store: domain + audit + event log +
                    #   credits ledger (atomic writes, survives restarts)
    supabase_store.py  # Supabase REST adapter SKELETON (mocked-HTTP tests only;
                    #   real project pending on Roger)
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
    trading.py      # paper buy/sell — shared by v1 orders and the executor.
                    #   Mode-gated: cross-mode ops raise CrossModeError;
                    #   real mode always raises LiveTradingDisabledError
    market.py       # v1 provider abstraction (Stooq, CoinGecko, Yahoo) + TTL cache
    portfolio.py    # valuation, P&L, allocation, returns — Decimal-exact.
                    #   PortfolioView carries mode + virtual flag
    store.py        # domain records + Store protocol (accounts carry
                    #   owner_user_id + mode; save_account for cash mutations)
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
uv run pytest                           # full suite (240 tests)
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

## Auth, modes, persistence (Phase 4)

### Auth (`app/auth.py`)

Account and financial endpoints require a Supabase JWT:

- `SUPABASE_JWT_SECRET` set → `Authorization: Bearer <jwt>` required.
  Tokens are verified with HS256 (stdlib HMAC, constant-time compare);
  wrong signature, expired, or missing tokens → **401**. The dependency
  `require_user` returns the token's `sub` as `user_id`.
- `SUPABASE_JWT_SECRET` unset → auth **DISABLED** with a loud startup
  warning; every request runs as the single dev user (`dev-user`), no token
  needed — the same graceful degradation the web frontend uses. Do not
  expose a dev-mode instance publicly.

Every account carries `owner_user_id`; every account-scoped endpoint
enforces ownership → **403** on mismatch (404 stays 404, so existence
doesn't leak). Public endpoints: `/api/health`, `/api/quotes/{symbol}`,
`/api/billing/credits/packs`, and the Stripe-signed
`/api/billing/webhook`.

### Modes (`app/modes.py`)

`Mode.REAL` / `Mode.EXPERIMENTAL` rides on accounts, positions,
transactions, snapshots, approvals, and brokerage orders. The domain
invariant is enforced in code, not just labels:

- No operation may read or mutate state across modes (`CrossModeError`).
  An experimental order can never touch real holdings, and vice versa.
- Real mode has **no execution path**: `execute_paper_buy/sell`,
  `InvestmentExecutor.propose/confirm/invest`, and
  `MockBrokerage(mode=REAL).submit_order` all raise
  `LiveTradingDisabledError("real execution is not configured…")` —
  HTTP **501**. Nothing is ever silently simulated as real.
- Experimental Mode is labeled virtual everywhere it surfaces:
  `"mode": "experimental", "virtual": true` on portfolio, order,
  transaction, and brokerage responses.

`POST /api/accounts` accepts `"mode": "real"` to create a real-mode
account (useful for testing the guardrails) — every money-moving call on
it fails loudly until a brokerage provider, credentials, and compliance
review exist (Roger's decision, still open).

### Persistence (`app/storage_sqlite.py`)

`FINKOW_STORE` selects the backend (`memory` | `sqlite` | `supabase`).
Default is **`sqlite`** (`data/finkow.db`, override with `FINKOW_DB_PATH`):
financial history must survive restarts, and SQLite is a file — not a new
database service — so it adds zero infrastructure. `memory` keeps the old
volatile behavior; `supabase` wires the skeleton adapter (below) and keeps
logs in memory with a warning.

The SQLite backend holds the domain store, the audit log, the agent event
log, and the credits ledger (including webhook idempotency keys — replays
can't double-credit after a restart). Writes are atomic per call under a
process lock (WAL journaling); decimals stay TEXT, never float.

`SUPABASE_URL` / `SUPABASE_SERVICE_KEY` wire `SupabaseStore`, a
**skeleton**: accounts, positions, transactions, and orders are implemented
and tested against mocked HTTP (no live calls — the real project is pending
on Roger); goals, plans, profiles, and approvals raise
`SupabaseNotImplementedError` honestly instead of pretending to work.

### Order lifecycle (`app/orders.py`)

Orders move through explicit, validated states — `draft` →
`awaiting_authorization` → `submitted` → `filled` (plus `partially_filled`
for future real providers) — with terminal `rejected` / `cancelled` /
`failed`. Illegal transitions raise `IllegalOrderTransitionError`; terminal
states are immutable. The paper path: propose → draft, human confirm →
awaiting_authorization → submitted → filled. The mock fills instantly and
the fill is recorded with `simulated: true` and **no provider order id** —
a mock record can never be confused with real execution.

- **Idempotency**: `POST /api/orders` and `POST /api/brokerage/orders`
  accept an `Idempotency-Key` header; a replay returns the original order
  instead of executing a duplicate trade.
- **Reconciliation, not assumption**: `POST /api/orders/{id}/reconcile`
  re-reads the recorded order and verifies it. A timeout does **not** prove
  failure — a stuck order is reported inconsistent with an investigation
  action, never assumed failed, never retried blindly. (The real-provider
  hook queries provider-side status first; see
  `docs/EXECUTION_PROVIDER.md`.)
- **Execution-provider contract**: `app/execution_provider.py` defines the
  `ExecutionProvider` Protocol a real brokerage must implement (submit,
  cancel, order status, positions sync, account info, market hours) and the
  exact data each method needs. No provider is chosen — Roger's decision,
  still open. Tests prove the mock can never satisfy the interface.

### Risk & authorization controls

The full control list, enforced in code (not just documented):

| Control | Where | Default |
|---|---|---|
| Per-trade USD cap | `OrderLifecycle.authorize` (`RiskLimits`), enforced on `POST /api/orders` and every executor path | $25,000 |
| Daily trades per account | same | 20 |
| Daily trades per user (across all their accounts — meaningful now that accounts have owners) | same | 50 |
| Human confirmation gate | `InvestmentExecutor.propose` → `confirm`; draft orders never execute on their own | required |
| Approval expiry | `confirm` rejects expired approvals and cancels their draft orders | 15 min |
| Mode separation | `check_mode` on every money-moving call; `CrossModeError` on mismatch | always |
| Real-mode execution guard | `LiveTradingDisabledError` → HTTP 501; nothing silently simulated | always |
| Output verifier | `app/governance/verifier.py`: schema + safety checks (PII, guaranteed-returns language) on agent outputs | always |
| Credit caps | `app/governance/metering.py`: paid-call budgets per account (`FINKOW_AISA_RATE_LIMIT_PER_MIN`) | 60/min |
| Idempotent submission | idempotency keys on order creation and billing webhooks | always |
| Audit trail | every money-affecting step appended to the audit log (`trade.executed`, `trade.skipped`, `order.cancelled`, `approval.*`) | always |

Breaches never drop silently: limit breaches and execution errors are
recorded on the order as `rejected` (with the reason) and returned as 4xx,
and skipped trades are audit-logged. Per-user daily limits count filled
orders plus legacy transactions exactly once — never double-counted.

## Environment

| Variable | Purpose | Default |
|---|---|---|
| `SUPABASE_JWT_SECRET` | HS256 secret for Supabase JWT auth; unset = auth disabled (dev mode, loud warning) | unset |
| `FINKOW_STORE` | storage backend: `memory` \| `sqlite` \| `supabase` | `sqlite` |
| `FINKOW_DB_PATH` | SQLite file location | `api/data/finkow.db` |
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | Supabase REST adapter (skeleton) | unset |
| `FINKOW_CORS_ORIGINS` | comma-separated browser origins | localhost:3000 |
| `FINKOW_AISA_RATE_LIMIT_PER_MIN` | paid-port rate budget | 60 |
| `AISA_API_KEY` | AIsa gateway (market/LLM/search) | unset → mocks |
| `STRIPE_SECRET_KEY` | Stripe billing (test mode) | unset → 503 |

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
- **Storage**: `FINKOW_STORE` selects the backend (default `sqlite`:
  `data/finkow.db` — survives restarts; `memory` for volatile dev/test;
  `supabase` for the skeleton adapter). `supabase/schema.sql` is the
  Postgres target. Domain code never touches storage details.

## Honest limits

- Auth is disabled unless `SUPABASE_JWT_SECRET` is set (dev mode: loud
  warning, single `dev-user`).
- The mock brokerage is a single shared sandbox, not per-user state.
- `SupabaseStore` is a skeleton: accounts/positions/transactions/orders
  only, tested against mocked HTTP; the real project is pending on Roger.
- Mock providers are deterministic demo data until `AISA_API_KEY` is set.
- No real-money execution exists or is reachable in this build
  (`submit_live_order` always raises; real-mode operations fail with 501).
- Investing involves risk; the app gives no guaranteed returns (the verifier
  rejects that language outright).
- Mock fills are labeled `simulated: true` with no provider order id —
  the API/UI can always distinguish them from real execution records.

## Endpoints

All endpoints except `/api/health`, `/api/quotes/{symbol}`,
`/api/billing/credits/packs`, and `/api/billing/webhook` (Stripe-signed)
require authentication (`Authorization: Bearer <Supabase JWT>` when
`SUPABASE_JWT_SECRET` is set; not needed in dev mode). Account-scoped
endpoints additionally enforce ownership → 403 on mismatch. Portfolio,
order, transaction, and brokerage responses carry
`"mode": "experimental" | "real"` and `"virtual": true/false`; order,
transaction, and brokerage responses additionally carry `"simulated": true`
and `"provider_order_id": null` on mock fills, so no client can mistake
them for real execution records.

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | liveness |
| POST | `/api/accounts` | create sandbox account ($100,000 virtual) |
| GET | `/api/quotes/{symbol}` | live quote (`AAPL`, `BTC`, …) |
| POST | `/api/orders` | virtual buy/sell through the order lifecycle (`Idempotency-Key` supported) |
| GET | `/api/orders/{id}` | order detail: status, fills, honesty markers |
| GET | `/api/accounts/{id}/orders` | order history for an account |
| POST | `/api/orders/{id}/reconcile` | reconcile an order against recorded state |
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
