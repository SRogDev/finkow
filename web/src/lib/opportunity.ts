import type { Opportunity } from "./finkow-client.ts";

/**
 * Presentation model for one opportunity (S16). The UI renders these
 * sections with progressive disclosure — summary first, deeper analysis
 * on demand — and never presents a discovery as a guaranteed outcome.
 */

/** The fixed paper-invest amount Finkow proposes per opportunity, in USD. */
export const OPPORTUNITY_INVEST_USD = 100;

/** Structural subset of Opportunity the presentation model needs. */
export type OpportunityLike = Pick<
  Opportunity,
  "id" | "title" | "category" | "summary" | "why" | "riskNote"
> &
  Partial<Pick<Opportunity, "evidence" | "proposal">>;

export interface OpportunityProposal {
  amountUsd: number;
  rationale: string;
  /** Always true: opportunity invests are paper-only, never real money. */
  virtual: true;
}

export interface OpportunitySections {
  /** What was discovered. */
  discovered: string;
  /** Why it may matter, in plain language. */
  whyItMatters: string[];
  /** The evidence supporting it. Empty when the agents have none yet. */
  evidence: string[];
  /** Principal risks and uncertainties, plus the no-guarantee line. */
  risks: string[];
  /** Whether any action is proposed. */
  proposedAction: OpportunityProposal | null;
  /** The next available action, spelled out in plain words. */
  nextAction: string;
}

export function opportunitySections(opp: OpportunityLike): OpportunitySections {
  return {
    discovered: opp.summary,
    whyItMatters: opp.why,
    // Never invent evidence: when the agents provide none, the card says so.
    evidence: opp.evidence ?? [],
    risks: [opp.riskNote, "Signals, not promises — no outcome here is guaranteed."],
    proposedAction: opp.proposal
      ? { amountUsd: opp.proposal.amountUsd, rationale: opp.proposal.rationale, virtual: true }
      : {
          amountUsd: OPPORTUNITY_INVEST_USD,
          rationale: "A fixed paper-invest amount while you learn.",
          virtual: true,
        },
    nextAction: `Tap once to invest $${OPPORTUNITY_INVEST_USD.toFixed(2)} in virtual money, or open the full analysis first. No real money moves — ever.`,
  };
}

/* ------------------------------------------------------------------ */
/* Guaranteed-outcome language scan (governance mirror, UI-side)       */
/* ------------------------------------------------------------------ */

/**
 * Patterns the UI must never render as promises. The backend governance
 * verifier bans these; this mirrors the check on UI copy (including the
 * mock data) so the frontend cannot reintroduce them.
 */
const GUARANTEE_PATTERNS: { pattern: RegExp; label: string }[] = [
  { pattern: /\bguarantee[ds]?\b/i, label: "guaranteed" },
  { pattern: /\brisk[-\s]?free\b/i, label: "risk-free" },
  { pattern: /\bsure[-\s]?thing\b/i, label: "sure thing" },
  { pattern: /\bcan'?t lose\b/i, label: "can't lose" },
  {
    pattern: /\bwill (?:make|earn|return|grow|rise|increase|double|profit)\b/i,
    label: "will make",
  },
];

export function findGuaranteedLanguage(text: string): string[] {
  return GUARANTEE_PATTERNS.filter(({ pattern }) => pattern.test(text)).map(({ label }) => label);
}
