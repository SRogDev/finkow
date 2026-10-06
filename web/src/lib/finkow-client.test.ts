import assert from "node:assert/strict";
import { test } from "node:test";
import { createFinkowClient } from "./finkow-client.ts";

/** Ticker-like symbols (e.g. "AAPL") must never leak into user-facing copy. */
const TICKER_RE = /\b[A-Z]{2,5}\b/;

test("createClient defaults to the mock adapter", async () => {
  const client = createFinkowClient();
  const goal = await client.createGoal("grow $1,000 over 5 years, low risk");
  assert.match(goal.id, /^goal-/);
  assert.equal(goal.text, "grow $1,000 over 5 years, low risk");
});

test("getPlan is deterministic for the same goal", async () => {
  const client = createFinkowClient();
  const goal = await client.createGoal("grow $1,000 over 5 years, low risk");
  const a = await client.getPlan(goal.id);
  const b = await client.getPlan(goal.id);
  assert.deepEqual(a, b);
  const total = a.allocations.reduce((sum, s) => sum + s.percent, 0);
  assert.equal(total, 100);
  for (const slice of a.allocations) {
    assert.ok(slice.label.length > 0);
    assert.ok(slice.why.length > 20, "each slice explains itself in plain language");
    assert.ok(!TICKER_RE.test(slice.label), `no tickers in labels: ${slice.label}`);
  }
});

test("getOpportunities returns at least 3 explained opportunities, no jargon", async () => {
  const client = createFinkowClient();
  const opps = await client.getOpportunities();
  assert.ok(opps.length >= 3, "radar must surface at least 3 opportunities");
  for (const opp of opps) {
    assert.ok(opp.title.length > 0);
    assert.ok(opp.summary.length > 20);
    assert.ok(opp.why.length >= 2, "every opportunity carries reasoning");
    assert.ok(opp.riskNote.length > 10, "every opportunity states its risk plainly");
    assert.ok(!TICKER_RE.test(opp.title), `no tickers in titles: ${opp.title}`);
  }
});

test("invest grows the portfolio and adds a position", async () => {
  const client = createFinkowClient();
  const before = await client.getPortfolio();
  const opps = await client.getOpportunities();
  const result = await client.invest(opps[0].id, 100);
  assert.match(result.positionId, /^pos-/);
  assert.ok(result.message.length > 0);
  const after = await client.getPortfolio();
  assert.equal(after.totalValueUsd, before.totalValueUsd + 100);
  assert.ok(after.positions.length >= before.positions.length);
});

test("invest rejects unknown opportunities and bad amounts", async () => {
  const client = createFinkowClient();
  await assert.rejects(() => client.invest("opp-nope", 100), /[Uu]nknown opportunity/);
  const opps = await client.getOpportunities();
  await assert.rejects(() => client.invest(opps[0].id, 0), /[Aa]mount/);
  await assert.rejects(() => client.invest(opps[0].id, -5), /[Aa]mount/);
});

test("getPortfolio speaks plain language", async () => {
  const client = createFinkowClient();
  const p = await client.getPortfolio();
  assert.ok(p.totalValueUsd > 0);
  assert.ok(p.pulseText.length > 0);
  assert.ok(p.pulseDetail.length > 20);
  for (const pos of p.positions) {
    assert.ok(!TICKER_RE.test(pos.label), `no tickers in positions: ${pos.label}`);
  }
});

test("getActivity returns ordered agent events", async () => {
  const client = createFinkowClient();
  const events = await client.getActivity();
  assert.ok(events.length >= 3);
  for (const e of events) {
    assert.ok(["Radar", "Pilot", "Planner", "Explainer"].includes(e.agent));
    assert.ok(e.text.length > 10);
  }
});

test("explain answers with grounded facts", async () => {
  const client = createFinkowClient();
  const ex = await client.explain("Why did my portfolio move today?");
  assert.ok(ex.answer.length > 40);
  assert.ok(ex.facts.length >= 2, "explanations cite their facts");
});
