# Finkow — MCP Spec (intended external-agent interface)

> Intended spec, 2026-10-16. **MCP is not implemented.** No MCP server, no
> MCP tool endpoints, and no external-agent authentication exist in this
> build (Phase 0 audit: "API surface for external clients — partially
> implemented; no MCP, no API keys, no auth").
>
> This document defines the intended capabilities, tool contracts, and
> safeguards so implementation (a later phase, after API auth + Real/Experimental
> mode separation) reuses the backend domain instead of inventing a parallel one.
> Nothing here describes working functionality.

## Purpose

External AI agents — a user's own assistant, a family office's research
agent, an advisor's tooling — interact with Finkow through MCP with **the
same trusted capabilities humans get through the conversational interface**,
and the same rules. One domain, two doors.

## Tool groups (adapted to the existing domain)

Tools are organized around outcomes, not internal functions. Proposed names
map to existing backend capabilities:

| Group | Candidate tool | Maps to (today's REST) | Implemented? |
|---|---|---|---|
| Portfolio | `get_portfolio` | `GET /api/accounts/{id}/portfolio`, `/api/goals/{id}/portfolio` | yes (paper) |
| Portfolio | `get_positions` | portfolio positions | yes (paper) |
| Portfolio | `get_transaction_history` | `GET /api/accounts/{id}/transactions`, `/api/accounts/{id}/history` | yes (paper) |
| Market/research | `get_quote` | `GET /api/quotes/{symbol}` | yes |
| Market/research | `get_opportunities` | `GET /api/radar/opportunities` | yes |
| Market/research | `analyze_symbol` | `GET /api/analyze/{symbol}` | yes |
| Market/research | `web_search` | WebSearchPort (AIsa) | yes (key-gated) |
| Goals | `create_goal` / `get_goal_plan` | `POST /api/goals`, `GET /api/goals/{id}/plan` | yes |
| Explanation | `explain` | `POST /api/explain` | yes |
| Investment preparation | `propose_trades` | `POST /api/executor/propose` (dry-run, nothing moves) | yes (paper) |
| Investment preparation | `get_approval_status` | pending approvals | yes (paper) |
| Investment preparation | `confirm_trades` | `POST /api/executor/confirm` | yes (paper) |
| Brokerage (real) | `submit_live_order` | `BrokeragePort.submit_live_order` | **NO — raises `LiveTradingDisabledError`** |

## Authorization model

1. **Client authentication first.** Every MCP client authenticates (API keys
   scoped to an OAuth-style client; exact mechanism to be defined at
   implementation). No anonymous clients.
2. **User authorization.** Tools act on behalf of a user; the server verifies
   the client may act for that user and enforces user→account ownership on
   every account-scoped call.
3. **Tool permissions (least privilege).** Permissions are granted
   explicitly per client: a read-only client can never submit or cancel
   orders; a research client cannot touch the confirmation gate. **An agent
   must not grant itself permissions** — permission changes require the
   user's explicit action through a separate channel.
4. **Mode restrictions.** Every tool call carries the mode (Real /
   Experimental); Experimental credentials cannot touch Real state and vice
   versa. Until Real Mode exists, all credentials are Experimental-only.
5. **Rate limits.** Per-client and per-user limits on paid operations (LLM /
   market data), enforced before provider calls; same spending governor as
   the human app (balance + daily/monthly caps).
6. **Validation.** All tool arguments validated server-side (schema + safety,
   including the ban on guaranteed-return language in generated content).

## Execution safeguards

- **Idempotent execution.** Mutating tools accept an idempotency key;
  retries with the same key never duplicate the operation.
- **Confirmations return pending, never false "executed".** The flow is
  research → proposal → human authorization → execution. A confirmation that
  awaits the user returns `status: "pending_authorization"`, never a claim
  of execution.
- **Human confirmation gate binds agents too.** The orchestrator's
  propose/confirm gate (15-minute approval expiry) applies identically to
  MCP-originated trade proposals. Agents propose; the human (or the user's
  pre-authorized policy, when such policies exist) disposes.
- **No secrets in client code, logs, or model-visible responses.** Keys,
   internal prompts, and raw credentials never appear in tool results.
- **Audit logging.** Every money-affecting MCP call is appended to the audit
  log with client id, user id, tool, arguments hash, outcome, and mode.

## What is NOT exposed

- **Real execution tools do not exist.** `submit_live_order` and any
  live-order tool are exposed **only when real execution actually exists**
  (brokerage decision + credentials + compliance review). Today it raises.
  Saying otherwise would be a lie.
- **No billing/credits administration** beyond the user's own balance reads.
  An agent cannot buy credits, change caps, or move Stripe money on the
  user's behalf.
- **No internal agent identities.** Specialists (LearningAgent, hunter,
  analyst, executor) stay internal; MCP exposes one Finkow capability
  surface, not the org chart.
- **No bulk exfiltration tools.** No "dump all users/accounts" operations;
  everything is user-scoped.

## Representative workflow (intended)

research → proposal → status, with mocks explicitly labeled:

1. Agent calls `get_opportunities(goal_id)` → ranked opportunities with
   plain-language reasoning and cited evidence.
2. Agent calls `analyze_symbol(symbol)` → fundamentals, valuation sanity,
   risks.
3. Agent calls `propose_trades(...)` → dry-run, returns a pending approval;
   nothing moves. Mode: Experimental (paper) in the current build.
4. User confirms (in-app or via pre-authorized policy) → `confirm_trades`
   executes the paper trades and returns the audit record.
5. Agent calls `get_approval_status` / `get_transaction_history` for verified
   execution details.

## Configuration (intended)

How to run/authenticate/configure/test tool contracts and authorization
boundaries is defined at implementation time, once API auth and mode
separation exist. The contract tests must cover: unauthorized execution
rejection, read-only client cannot submit, agent cannot self-escalate
permissions, and pending-authorization (never false-executed) confirmations.
