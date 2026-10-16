# Execution Provider Interface

**Status:** interface defined, no provider chosen. Choosing a brokerage
provider is **Roger's decision** and stays **OPEN** — this document defines
what a real integration must supply and documents exactly what is missing.
Nothing here invents a provider or its behavior.

Related code: `api/app/execution_provider.py` (the `ExecutionProvider`
Protocol and data contracts), `api/app/orders.py` (order lifecycle),
`api/app/brokerage.py` (the mock — see "Why the mock can never satisfy
this interface").

## The contract

A real execution integration implements `ExecutionProvider`:

| Method | What the provider must supply |
|---|---|
| `submit(account, request)` | Route an order. Needs: provider credentials, the provider's account id, symbol/side/qty, order type, time in force, **idempotency key** (the provider dedupes on it). Returns the **provider's own order id**. |
| `cancel(account, provider_order_id)` | Cancel an open order; returns its final provider-side status. |
| `get_order(account, provider_order_id)` | Provider-side order status. **This is the reconciliation query**: a timeout does NOT prove failure — this is called BEFORE any retry. |
| `list_open_orders(account)` | All non-terminal provider-side orders for the account. |
| `sync_positions(account)` | Authoritative positions from the provider (settlement truth). |
| `get_account_info(account)` | Authoritative cash / buying power from the provider. |
| `market_hours()` | Trading calendar: IANA timezone, regular open/close, extended-hours support, observed holidays. |

Supporting contracts (all in `execution_provider.py`):

- `ProviderOrderRequest` — symbol, side, qty, order type, time in force,
  limit/stop prices, and a **required** idempotency key.
- `ProviderOrderResult` — the provider's order id (**required, non-empty**
  for anything claimed as real), status as `OrderStatus`, filled qty, avg
  fill price, submitted-at, and the raw provider payload for audit.
- `ProviderAccountRef` — Finkow account id + owner + the broker's account
  id. Always `Mode.REAL`; providers never see experimental accounts.
- `ProviderAccountInfo` — cash, buying power, currency, live flag.
- `ProviderCapabilities` — honest capability advertisement:
  `real_execution`, `provides_provider_order_ids`, `partial_fills`,
  `real_settlement`, supported order types, fractional support, rate
  limit, market-hours timezone.
- `assert_real_execution_result(result)` — the gate the (unwired) real path
  runs on every provider result. Rejects anything simulated or missing a
  provider order id with `RealExecutionContractError`.

## What a real provider integration must supply

1. **Credentials** — API key/secret or OAuth, stored server-side only
   (Secure Vault / env). Never in client code, logs, or model-visible
   responses.
2. **Account mapping** — Finkow account id → the broker's account id
   (`ProviderAccountRef.provider_account_id`).
3. **Supported order types** — which of market/limit/stop/etc. the broker
   accepts, plus fractional-share support.
4. **Market hours / timezone handling** — `MarketHours`: the IANA timezone
   the broker routes under, regular session open/close, extended hours,
   holiday calendar. Orders outside sessions must be queued or rejected
   explicitly — never silently "filled" at a mock price.
5. **Rate limits** — requests/minute the integration may make; the
   lifecycle's reconcile path must respect them (no blind retry loops).
6. **Settlement truth** — `sync_positions` / `get_account_info` are the
   authoritative source after fills; local records are reconciled against
   them, not the other way around.
7. **Error taxonomy** — provider errors map onto `OrderStatus`
   (`rejected` on validation, `failed` on unknown-outcome errors, never
   assumed-failed on timeout).
8. **Idempotency** — the provider dedupes on `ProviderOrderRequest.
   idempotency_key`; the lifecycle never resubmits a key without first
   reconciling.

## What is MISSING today (pending Roger)

- [ ] **The brokerage provider decision** — no provider has been chosen.
  This is Roger's call, not the implementer's. Blocks: any real execution
  path, real-mode order submission, execution UI honesty.
- [ ] **Credentials** — no API keys exist for any broker.
- [ ] **Compliance review** — local securities regulations for the
  operating jurisdiction(s); required before any real-money path.
- [ ] **Explicit user opt-in** — real execution needs a deliberate,
  informed enablement step; it must never be a silent default.

Until all four are resolved, every real-mode attempt raises
`LiveTradingDisabledError` (HTTP 501) — never a silent mock fallback.

## Why the mock can never satisfy the interface

`MockBrokerage` / `MockExecutionProvider` satisfy the Protocol's *shape*
but fail its *contract*, by construction:

- **No provider order ids** — every mock result has
  `provider_order_id=None`. `assert_real_execution_result` rejects it, so
  mock output can never flow into a real path.
- **No partial fills** — the mock fills instantly and completely.
- **No real settlement** — `sync_positions`/`get_account_info` are virtual.
- **No market-hours enforcement** — the mock fills 24/7 at mock prices.
- **Refuses real mode** — constructed or called with `Mode.REAL`, every
  submission raises `LiveTradingDisabledError`. The mock never simulates
  a real order.

Tests proving this live in `api/tests/test_execution_provider.py` and
`api/tests/test_orders_api.py` (mock fills carry `simulated: true`,
`mode: experimental`, `provider_order_id: null`).

## Reconciliation, not assumption

A timeout does NOT prove failure. Before any retry, the lifecycle
reconciles: `OrderLifecycle.reconcile(order_id)` re-reads the recorded
order and, once a provider is wired, queries
`ExecutionProvider.get_order(provider_order_id)` for provider-side truth.
A stuck order is reported **inconsistent with an investigation action** —
never marked failed on assumption, never retried blindly. The mock has no
provider to query, so a stuck mock order is an internal inconsistency to
investigate.
