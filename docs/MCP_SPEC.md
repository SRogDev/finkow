# Finkow — MCP Spec (implemented external-agent interface)

> **IMPLEMENTED 2026-10-16** (local build; commit pending — GitHub access
> suspended). The MCP server exposes **only implemented capabilities**,
> reusing the backend domain modules directly — no parallel financial
> domain, no invented provider behavior. Transport: MCP stdio (JSON-RPC
> 2.0) via the official `mcp` Python SDK (v2 `MCPServer`), structured
> output per tool.
>
> What remains *intended but not implemented* is listed at the bottom.
> Nothing in this document describes working functionality that isn't —
> simulated/paper state is labeled `virtual: true` in every financial
> response.

## Purpose

External AI agents — a user's own assistant, a family office's research
agent, an advisor's tooling — interact with Finkow through MCP with **the
same trusted capabilities humans get through the conversational interface**,
and the same rules. One domain, two doors.

## Running the server

```bash
cd api
uv run python -m app.mcp.server
```

The server speaks JSON-RPC 2.0 over stdio (`initialize`, `tools/list`,
`tools/call`, proper error codes). Any MCP client (Claude Desktop,
`mcp` CLI, custom agents) can launch it as a subprocess.

## Authentication

- `FINKOW_MCP_API_KEYS`: comma-separated entries, each
  `<secret>[:<perms>[:<user_id>]]`.
  - `<secret>`: the key the client presents in the per-call `api_key`
    argument (stdio has no headers). Compared in constant time
    (`hmac.compare_digest`).
  - `<perms>`: `read` (default) or `read+propose`. `read` covers every
    read-only tool; `read+propose` additionally allows
    `prepare_investment_proposal`. **An agent must not grant itself
    permissions** — keys and permission sets are operator configuration.
  - `<user_id>`: the user the key acts on behalf of (defaults to the dev
    user). Account ownership is enforced against this user exactly as in
    the REST app (`require_account_owner`).
- No keys configured → every call is rejected (safe by default).
- Keys, internal prompts, and raw credentials never appear in tool
  results, logs, or audit entries (audit stores an arguments hash only).

## Tool catalog

All twelve tools, their permission, and read-only vs mutating marks:

| Tool | Permission | Mutates? | Maps to (backend) |
|---|---|---|---|
| `get_portfolio` | read | no | portfolio valuation (`value_portfolio`) |
| `get_positions` | read | no | portfolio positions, valued at quotes |
| `get_transaction_history` | read | no | `store.list_transactions` |
| `get_portfolio_performance` | read | no | `store.list_snapshots` |
| `get_market_data` | read | no | primary market-data port (labeled `mock` without an AIsa key) |
| `search_investment_opportunities` | read | no | `OpportunityRadar.scan` |
| `analyze_asset` | read | no | `Orchestrator.analyze` (FinancialAnalyst) |
| `analyze_portfolio` | read | no | computed diagnostics from `value_portfolio` |
| `get_activity_history` | read | no | `EventLog.list` |
| `prepare_investment_proposal` | **read+propose** | dry-run only | `InvestmentExecutor.propose` → DRAFT orders, `pending_authorization` |
| `validate_investment_action` | read | no | dry risk-control check (no orders, no money) |
| `get_order_status` | read | no | order or approval status (incl. draft orders) |

Name mapping from the earlier intended draft: `get_quote` →
`get_market_data`, `get_opportunities` → `search_investment_opportunities`,
`analyze_symbol` → `analyze_asset`, `propose_trades` →
`prepare_investment_proposal`, `get_approval_status` → `get_order_status`.
`web_search`, goals, and `explain` remain REST-only for now (see below).

## The execution boundary (non-negotiable)

- **There is deliberately NO execution tool.** Real execution does not
  exist in this build (`submit_live_order` raises
  `LiveTradingDisabledError` by design), and paper submission stays behind
  the human confirmation gate.
- `prepare_investment_proposal` returns `status: "pending_authorization"`
  with what the human must approve (in-app, 15-minute expiry) — never a
  false executed claim. The tool description itself states this boundary.
- `validate_investment_action` is a dry check; passing it is not a
  guarantee of execution.

## Authorization model (implemented)

1. **Client authentication first.** Every call carries `api_key`;
   unknown keys are rejected (`-32001`); failures are audit-logged.
2. **User authorization.** Tools act on behalf of the key's `user_id`;
   account ownership is enforced on every account-scoped call.
3. **Tool permissions (least privilege).** A read-only key calling
   `prepare_investment_proposal` gets `-32002` permission denied.
4. **Mode restrictions.** Every tool takes `mode` (default
   `experimental`); `real` is rejected (`-32004`). Every response carries
   `mode` and `virtual: true` — simulated state can never be mistaken for
   real money.
5. **Rate limits.** Per-key fixed-window budget
   (`FINKOW_MCP_RATE_LIMIT_PER_MIN`, default 60/min), reusing
   `governance/rate_limiter.py`; exhaustion returns `-32003`.
6. **Validation.** All arguments validated server-side (strict pydantic
   input/output schemas; `-32602`/`-32006` on bad input), including the
   ban on guaranteed-return language in generated content.
7. **Audit logging.** Every tool call — success, rejection, or failure —
   is appended to the audit log with actor `mcp:<key_id>`, the tool,
   an arguments hash, outcome, and mode. No secrets stored.
8. **Idempotency.** `prepare_investment_proposal` accepts an
   `idempotency_key`; retries return the original proposal
   (`idempotent_replay: true`) without duplicate draft orders. The
   dedup record is process-local to the MCP server; the store-level
   order idempotency keys remain on the draft orders.

## Error semantics

Tool failures return MCP results with `isError: true` and a JSON
`{"code", "message"}` payload (the SDK prefixes it with
`Error executing tool <name>:`). Codes:

| Code | Meaning |
|---|---|
| `-32001` | authentication failed (unknown/missing key) |
| `-32002` | permission denied (tool not in the key's permission set) |
| `-32003` | rate limited (per-key budget exhausted) |
| `-32004` | mode rejected (real mode requested; MCP is experimental-only) |
| `-32005` | not found (account / order / approval / symbol) |
| `-32006` / `-32602` | invalid input / invalid params |
| `-32007` | backend failure (market data, credits, real-path refusal) |
| `-32603` | internal error (logged server-side) |

Protocol-level failures (`initialize`, unknown method, malformed JSON)
use the standard JSON-RPC codes via the SDK.

## Market data honesty

- MCP market data uses the **same primary provider** as the human app
  (AIsa when `AISA_API_KEY` is set, the deterministic mock otherwise).
- The free live fallback chain is **disabled on the MCP path**: an
  unknown symbol returns `-32005` NOT_FOUND instead of triggering a
  surprise external call. The `provider` field names the source in every
  quote (`mock` in this build — zero live calls in tests).
- Mock/deterministic data is labeled wherever it surfaces; nothing is
  presented as live market truth.

## Representative workflow (implemented, tested)

research → proposal → status, with mocks explicitly labeled:

1. Agent calls `search_investment_opportunities(symbols="AAPL,MSFT")` →
   ranked opportunities with reasoning (mock provider labeled).
2. Agent calls `analyze_asset(symbol="AAPL")` → verdict, risk flags,
   plain-language summary.
3. Agent calls `prepare_investment_proposal(account_id, allocations)` →
   dry-run, DRAFT orders created, returns `status: "pending_authorization"`;
   nothing moves. Mode: experimental (virtual) in this build.
4. **Human confirms in the app** (or a pre-authorized policy, when such
   policies exist) — the gate binds agents exactly as it binds the REST
   app. MCP has no confirm/execute tool.
5. Agent calls `get_order_status(approval_id)` → pending authorization
   with the draft orders, or the resolved status afterwards.

Covered by `api/tests/test_mcp.py` (36 tests): stdio round-trips (spawn,
list, call each read tool, structured output + mode fields), auth
boundaries (bad key, read-only vs propose, rate limit, real-mode
rejection), audit-every-call, idempotent propose, and the full workflow.

## What is NOT exposed (unchanged)

- **Real execution tools do not exist.** `submit_live_order` and any
  live-order tool are exposed **only when real execution actually exists**
  (brokerage decision + credentials + compliance review). Today it raises.
  Saying otherwise would be a lie.
- **No confirm/execute over MCP.** The human confirmation gate lives in
  the app; agents propose, humans dispose.
- **No billing/credits administration** beyond the user's own balance
  reads. An agent cannot buy credits, change caps, or move Stripe money.
- **No internal agent identities.** Specialists stay internal; MCP exposes
  one Finkow capability surface.
- **No bulk exfiltration tools.** Everything is user-scoped.
- REST-only for now (candidates for later MCP phases): `web_search`,
  goal creation/planning, `explain`, the conversational harness
  (`/api/harness/run`), and billing checkout. Nothing about them is
  claimed over MCP.

## Configuration reference

| Variable | Default | Purpose |
|---|---|---|
| `FINKOW_MCP_API_KEYS` | (empty → all rejected) | `<secret>[:<perms>[:<user_id>]]`, comma-separated |
| `FINKOW_MCP_RATE_LIMIT_PER_MIN` | `60` | per-key tool-call budget per minute |
| `FINKOW_STORE` / `FINKOW_DB_PATH` | `sqlite` / `api/data/finkow.db` | storage backend, shared with the REST app |
| `AISA_API_KEY` | (unset → mock providers) | switches market/LLM/search to AIsa (metered) |
