import assert from "node:assert/strict";
import { test } from "node:test";
import { createFinkowClient } from "./finkow-client.ts";
import {
  findGuaranteedLanguage,
  OPPORTUNITY_INVEST_USD,
  type OpportunityLike,
  opportunitySections,
} from "./opportunity.ts";

const SAMPLE: OpportunityLike = {
  id: "opp-sample",
  title: "Sample trend",
  category: "Growth",
  summary: "Something interesting is happening.",
  why: ["Reason one.", "Reason two."],
  riskNote: "Prices can swing.",
  evidence: ["Agents logged two weeks of steady buying."],
  proposal: { amountUsd: 100, rationale: "A small virtual slice." },
};

test("opportunitySections exposes the full S16 presentation contract", () => {
  const s = opportunitySections(SAMPLE);
  assert.equal(s.discovered, SAMPLE.summary);
  assert.deepEqual(s.whyItMatters, SAMPLE.why);
  assert.deepEqual(s.evidence, SAMPLE.evidence);
  assert.ok(s.risks.length >= 1, "principal risks must be present");
  assert.ok(
    s.risks.some((r) => r.includes("guaranteed")),
    "risks must carry the no-guarantee honesty line",
  );
  assert.equal(s.proposedAction?.amountUsd, 100);
  assert.equal(s.proposedAction?.virtual, true);
  assert.ok(s.nextAction.length > 10, "next available action must be spelled out");
});

test("opportunitySections falls back honestly when evidence is missing", () => {
  const s = opportunitySections({ ...SAMPLE, evidence: undefined });
  assert.deepEqual(s.evidence, [], "must not invent evidence");
});

test("opportunitySections defaults the proposal to the fixed paper amount", () => {
  const s = opportunitySections({ ...SAMPLE, proposal: undefined });
  assert.equal(s.proposedAction?.amountUsd, OPPORTUNITY_INVEST_USD);
  assert.equal(s.proposedAction?.virtual, true);
});

test("findGuaranteedLanguage flags promise-style copy", () => {
  assert.deepEqual(findGuaranteedLanguage("Returns are guaranteed."), ["guaranteed"]);
  assert.deepEqual(findGuaranteedLanguage("This will make you rich."), ["will make"]);
  assert.deepEqual(findGuaranteedLanguage("A risk-free win."), ["risk-free"]);
  assert.deepEqual(findGuaranteedLanguage("Steady buying over two weeks."), []);
});

test("mock opportunity copy contains no guaranteed-outcome language", async () => {
  const client = createFinkowClient();
  const opps = await client.getOpportunities();
  assert.ok(opps.length > 0);
  for (const opp of opps) {
    // S16 completeness: summary, why, risk note, evidence, and a proposal
    // must all be present before the card can present them.
    assert.ok(opp.summary.trim().length > 0, `${opp.id}: summary required`);
    assert.ok(opp.why.length > 0, `${opp.id}: why required`);
    assert.ok(opp.riskNote.trim().length > 0, `${opp.id}: risk note required`);
    assert.ok((opp.evidence?.length ?? 0) > 0, `${opp.id}: evidence required`);
    assert.ok((opp.proposal?.amountUsd ?? 0) > 0, `${opp.id}: proposal required`);
    const copy = [opp.title, opp.summary, ...opp.why, opp.riskNote, ...(opp.evidence ?? [])].join(
      " ",
    );
    assert.deepEqual(findGuaranteedLanguage(copy), [], `${opp.id}: no guaranteed language`);
  }
});
