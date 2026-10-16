# Finkow — Product Reframe (authoritative spec)

> **Status:** authoritative product spec (single source of truth), 2026-10-16.
> Everything that contradicts it elsewhere in this repo is stale and must be
> labeled historical, not followed.
>
> Supersedes the 2026-10-06 "owner directive" version of this file (that
> version wrongly claimed Elastic License 2.0; the committed `LICENSE` file is
> MIT and MIT wins — resolved in Phase 1).
>
> `docs/product-context.md` is the v1 archive (2026-09-26); where it conflicts
> with this document, this document wins.

## One-liner

An AI-native investment platform: tell Finkow your goal in plain language;
one intelligent system researches, plans, manages, and explains — paper
trading now, real money only behind an explicit, authorized path later.

## What Finkow is

- **An investment platform, first.** It exists to help people grow money
  through investing. It is not a budgeting app, not an expense tracker, not a
  generic chatbot, and not a manual trading terminal.
- **AI as the primary interaction.** One intelligent system the user talks to
  in natural language. Specialist agents (research, planning, execution,
  explanation) are internal implementation details — never the user's mental
  model.
- **Human-accessible.** Plain language, progressive disclosure, zero finance
  jargon by default. Financial intuition is a side effect, not the product.
- **For humans and external agents alike.** The same trusted capabilities,
  exposed to people through the conversational interface and to authorized
  external AI agents through MCP — one domain, two doors. (See
  `docs/MCP_SPEC.md` and `docs/KEY_SUCCESS.md`.)

## What Finkow is not

- A brokerage. There is no real-money execution and no real brokerage
  integration in the current build. Nothing here moves real money.
- A budget/expense/household-finance tool.
- A promise of returns. No guaranteed-return language anywhere in the
  product; the output verifier rejects it.

## Real Mode vs Experimental Mode

The two modes are the product's core trust boundary. They are defined by
which capital is at stake, and their state must never mix:

| | Experimental Mode | Real Mode |
|---|---|---|
| Capital | virtual/paper only | user's real money |
| Execution | simulated fills against provider port | real brokerage integration |
| State | separate portfolios, holdings, cash, orders, transactions, credits, agent authorizations | separate everything — no shared records |

Rules:

1. **No state mixing.** Real and Experimental state (portfolios, holdings,
   cash, orders, transactions, execution results, strategy state, agent
   authorizations) live in disjoint domains. A test must prove simulated
   operations cannot contaminate real state, and vice versa.
2. **Never silently mock for real.** A missing real-money integration is
   reported as missing, never replaced by a mock behind the scenes.
3. **Simulated is always labeled simulated.** A simulated execution is never
   displayed as a real one — not in the UI, not in MCP tool results, not in
   logs the user can see.
4. **The live path stays disabled** until a brokerage decision (Roger's),
   credentials, and compliance review exist. Today, `submit_live_order`
   always raises.

## Capabilities (intended product)

- **Conversational home.** Natural-language goal input, persistent portfolio
  indicator (value, movement, link to the portfolio view; virtual capital
  always labeled), useful default state (input, portfolio context, recent
  activity, discoveries) — no empty screens, no artificial activity.
- **Portfolio management.** Total value → period performance → gains/losses
  → allocation → positions → recent transactions → full history. Realized vs
  unrealized gains, deposits/withdrawals, fees, and cash are distinguished;
  deposits are never presented as gains.
- **Financial history.** Chronological transaction history with explicit
  statuses (proposed / submitted / partially filled / filled / rejected /
  cancelled / failed) and only verified execution details.
- **Intelligent activity.** An activity inbox in three states — requires
  attention / in progress / completed — each item communicating what, why,
  status, and the next action. A running task is never shown as completed.
- **Actionable discoveries.** Opportunities are presented as: what was
  discovered, why it may matter, supporting evidence, principal
  risks/uncertainties, whether action is proposed, and the next available
  action — never as guaranteed outcomes. Detecting ≠ executing.
- **Trust & safety.** Human confirmation gate on money-affecting actions;
  append-only audit of every money-affecting operation; PII redaction on
  stored text; plain-language "why" for every agent action.

## External-agent access

External AI agents interact with Finkow through MCP, reusing the same
backend and the same rules as the human app (client auth, account
authorization, tool permissions, mode restrictions, rate limits, audit
logging, idempotent execution). MCP execution tools are exposed **only when
the corresponding execution capability actually exists** — today that means
no real-execution tools at all. Full contract: `docs/MCP_SPEC.md`.
The business hypothesis behind this is recorded — as a hypothesis — in
`docs/KEY_SUCCESS.md`.

## Current capabilities vs intended product (honest)

As of 2026-10-16. This is the implemented reality; everything above this
section is the intended product.

- **Paper trading only.** `MockBrokerage` fills paper orders instantly.
  There is no real-money code path and none is reachable in this build.
- **In-memory state.** The `InMemoryStore` implements the `Store` protocol;
  restart wipes everything (audit log, event log, credits ledger included).
  Supabase is pending (schema exists, adapter not built).
- **No API auth.** FastAPI endpoints have no authentication and no
  user→account ownership checks. A Supabase sign-in gate exists in the web
  app but is disabled when unconfigured.
- **No mode separation yet.** Real/Experimental mode separation is defined
  here but not yet enforced in the domain (Phase 4 of the evolution plan).
- **Market data, partially live.** Port chain AIsa → keyless direct
  (Yahoo/Stooq/CoinGecko) → deterministic mock, TTL-cached; live freshness
  not verified in the latest audit (no keys on the audit machine).
- **LLM/search cost real.** The agent-money layer is implemented and
  simulated end to end with exact balances: users buy API credits
  ($5/$20/$50 packs) via Stripe Checkout; agents spend them on paid AIsa
  calls with per-call metering from AIsa's actual cost header, balance plus
  daily/monthly caps enforced before each call, 402 + top-up link on
  exhaustion. Stripe and AIsa keys are required for the live path.
- **What is implemented and verified:** 187 backend tests + 36 web tests
  green (2026-10-16 audit): orchestrator + 4 specialists (LearningAgent,
  OpportunityHunter, FinancialAnalyst, InvestmentExecutor), human
  confirmation gate (15-min approval expiry), governance (output verifier,
  audit log, rate limiter, PII filter), credits ledger, decimal-exact
  portfolio math, paper buy/sell + one-tap invest, goal planning,
  opportunity radar, grounded explainer.
- **What is not implemented:** real execution, mode separation, API auth,
  persistence, MCP, background workers, order lifecycle beyond
  proposed/filled/rejected (no partial fills, no cancel-submitted, no
  timeout reconciliation).

## Non-negotiables

1. Financial truth: simulated is never presented as real.
2. AI-native: one intelligent system; specialists stay internal.
3. Investment-first: not budgeting, not a tracker, not a terminal.
4. No guaranteed-return language anywhere.
5. Human stays in control of execution: detecting ≠ executing; confirmation
   gates bind.
6. External agents get the same trusted capabilities as humans — no more, no less.
7. English code, comments, and docs. MIT license (per the committed `LICENSE`).
