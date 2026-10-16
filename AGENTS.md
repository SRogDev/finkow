# AGENTS.md — Finkow working agreement

Repo-local conventions for anyone (human or agent) working on Finkow.
Authoritative product spec: `docs/PRODUCT_REFRAME.md`. Visual truth:
`design-system/finkow/MASTER.md`.

## Engineering discipline

- **All coding through the `gentle-ai` skill** (ODD routing, TDD evidence,
  RDD self-review). No exceptions.
- **All frontend work through `ui-ux-pro-max`** — run
  `scripts/search.py --design-system` first for the design system, then
  implement — plus `vercel-react-best-practices` on all React/Next.js code.
  No exceptions.
- **Python via `uv` only** — `uv venv`, `uv sync`, `uv run`. Never
  `python -m venv` + pip, never bare `requirements.txt`. uv binary:
  `~/.local/bin/uv`.

## Language and docs

- **English** for code, comments, and docs. README touch-up ships in the
  same PR as every significant change (English, current, no invented claims).

## Workflow

- One PR = one logical change against `main`; squash-merge; never push
  directly to `main`. PR bodies carry verifiable evidence (test counts,
  SHAs). Muse merges his own PRs (Roger's standing authorization).
- **While GitHub is suspended (403 since 2026-10-16):** no GitHub calls at
  all — no pushes, no PRs. Local commits only, one commit per phase, so each
  becomes a PR on unblock. The PR workflow resumes immediately on access
  restoration.

## Financial honesty (non-negotiable)

- Simulated trading is never described as real or available. No
  real-money claims until a real execution path is verified end to end.
- Real/Experimental modes never share state (portfolios, holdings, cash,
  orders, transactions, authorizations).
- Never silently replace a missing real integration with a mock.
- No guaranteed-return language anywhere — in code, UI copy, or docs. The
  output verifier enforces this.

## Gates

- No live API calls without Roger's keys. Stripe test mode only.
- The brokerage provider decision is Roger's — define the interface,
  document the gap, never choose a provider.
- No new database, orchestration framework, brokerage, or visual library
  without a concrete reason from an audit.
