# Finkow — Key Success

> Strategic mission document, 2026-10-16. Written per SPEC §8 (S19):
> the external-agent-via-MCP direction is a **hypothesis to validate**,
> not a proven model. The 7 product principles are commitments, not
> predictions. Metrics are candidates, not targets.

## Strategic mission

Build the investment platform where one intelligent system serves both
people and their AI agents: humans talk to Finkow in plain language;
authorized external agents use the same trusted capabilities through MCP.
Reliability, transparency, and control first — especially where real money
will eventually move.

## The agent-first hypothesis (unvalidated)

**Hypothesis:** external agents connecting to Finkow via MCP become the
primary distribution and monetization channel — Finkow as the trusted
execution and intelligence layer behind other people's agents.

This is **not** a proven model. Evidence we do not have yet: any external
agent integrated, any willingness-to-pay from agent operators, any
retention or trust signal from agent-mediated users. The hypothesis must be
validated, in order, by:

1. The domain being genuinely trustworthy (mode separation, audit, honest
   labeling) — no agent will build on a platform that mixes simulated and
   real.
2. The human product being good — an MCP surface nobody trusts as a human
   product will not be trusted by agents either.
3. A small number of real external-agent pilots (the user's own assistant,
   an advisor's tooling) with measured behavior: what they call, what they
   confirm, where they hit friction.

Until then, MCP stays a scoped intention (see `docs/MCP_SPEC.md`), built
behind auth and mode separation, exposing only implemented capabilities.

## The 7 product principles

1. **Investment-first.** Finkow is about growing money through investing —
   never a budgeting app, expense tracker, generic chatbot, or manual
   terminal.
2. **One intelligent system.** The user experiences one Finkow; specialist
   agents are internal implementation details.
3. **Financial truth is non-negotiable.** Simulated is never presented as
   real; modes never mix; the audit trail is complete.
4. **Trust through transparency.** Every agent action shows its why in plain
   language. No black-box moves with the user's money — virtual or real.
5. **The human stays in control.** Detecting ≠ executing. Money-affecting
   actions pass through confirmation; approval is explicit and expirable.
6. **Same capabilities for humans and authorized agents.** No second-class
   API, no privileged backdoor — one domain, equal rules.
7. **Evidence over claims.** No guaranteed-return language, no vanity
   metrics, no unimplemented capability described as working.

## Candidate metrics (not targets; never tool-call volume alone)

Product health:
- Goal completion: share of stated goals that reach a funded plan and
  sustained paper activity.
- Explanation depth: share of agent actions the user actually reads the
  "why" for.
- Discovery quality: share of opportunities that lead to a deliberate
  decision (act or explicitly dismiss), not passive scrolling.
- Trust signals: confirmation-gate abandonment rate, audit-record views,
  plain-language question rate ("why did my portfolio move?").

Trust/operational integrity:
- Audit cleanliness: share of money-affecting operations with complete
  audit records (target: 100% by construction).
- Honest-labeling incidents: count of simulated results shown without
  simulation labeling — must stay at zero.
- Cap-exhaustion handling: share of 402 responses that result in a
  successful top-up vs abandonment.

Agent-channel hypothesis (only once pilots exist):
- External-agent integrations active; permission-revoke rate per client
  (a low revoke rate plus continued use is the real trust signal);
  human-confirmation latency on agent-proposed trades;
  share of agent workflows completing research → proposal → confirmed
  execution without support intervention.

**Explicitly not success metrics:** raw tool-call volume, endpoint hit
counts, or any number that grows when agents do more work for no user
benefit.
