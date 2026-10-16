import assert from "node:assert/strict";
import { test } from "node:test";
import { createFinkowClient, HttpFinkowClient } from "./finkow-client.ts";

type Json = Record<string, unknown>;

function mockFetch(routes: Record<string, { status?: number; body: Json }>) {
  const calls: { url: string; init?: RequestInit; body: Json | null }[] = [];
  (globalThis as { fetch?: unknown }).fetch = async (url: unknown, init?: RequestInit) => {
    const urlStr = String(url);
    const path = urlStr.replace(/^https?:\/\/[^/]+/, "");
    let parsed: Json | null = null;
    try {
      parsed = init?.body ? (JSON.parse(String(init.body)) as Json) : null;
    } catch {
      parsed = null;
    }
    calls.push({ url: urlStr, init, body: parsed });
    const route = routes[`${init?.method ?? "GET"} ${path}`];
    if (!route) {
      return new Response(JSON.stringify({ detail: "not mocked" }), { status: 500 });
    }
    return new Response(JSON.stringify(route.body), { status: route.status ?? 200 });
  };
  return calls;
}

const GOAL_BODY = {
  goal_id: "goal-9",
  account_id: "acc-9",
  amount: "1000.00",
  text: "grow $1,000",
  created_at: "2026-10-16T10:00:00Z",
};

test("createGoal posts to the real /api/goals endpoint and maps the account", async () => {
  const calls = mockFetch({ "POST /api/goals": { body: GOAL_BODY } });
  const client = new HttpFinkowClient({
    baseUrl: "http://api.test",
    getToken: async () => "tok-1",
  });
  const goal = await client.createGoal("grow $1,000");
  assert.equal(goal.id, "goal-9");
  assert.equal(goal.accountId, "acc-9");
  assert.equal(goal.text, "grow $1,000");
  assert.equal(calls[0].url, "http://api.test/api/goals");
  assert.deepEqual(calls[0].body, { text: "grow $1,000" });
  const headers = new Headers(calls[0].init?.headers as HeadersInit);
  assert.equal(headers.get("authorization"), "Bearer tok-1");
});

test("getPlan maps the backend plan shape, weights to percents", async () => {
  mockFetch({
    "GET /api/goals/goal-9/plan": {
      body: {
        goal_id: "goal-9",
        summary_plain: "A calm plan.",
        horizon_years: 5,
        risk_level: "low",
        allocations: [
          { symbol: "AAPL", weight: "0.5000", rationale: "Steady earner." },
          { symbol: "CASH", weight: "0.5000", rationale: "Dry powder." },
        ],
      },
    },
  });
  const client = new HttpFinkowClient({ baseUrl: "http://api.test" });
  const plan = await client.getPlan("goal-9");
  assert.equal(plan.goalId, "goal-9");
  assert.equal(plan.summary, "A calm plan.");
  assert.equal(plan.horizon, "5 years");
  assert.equal(plan.risk, "low");
  assert.equal(plan.allocations.length, 2);
  assert.equal(plan.allocations[0].percent, 50);
  assert.ok(plan.allocations[0].why.length > 0);
});

test("getPortfolio surfaces mode/virtual flags and all-time change honestly", async () => {
  mockFetch({
    "GET /api/accounts/acc-9/portfolio": {
      body: {
        account_id: "acc-9",
        mode: "experimental",
        virtual: true,
        cash: "900.00",
        initial_cash: "1000.00",
        total_value: "1050.00",
        total_return: "50.00",
        total_return_pct: "5.00",
        allocation: { AAPL: "0.1000" },
        as_of: "2026-10-16T10:00:00Z",
        positions: [
          {
            symbol: "AAPL",
            quantity: "1",
            avg_cost: "100.00",
            price: "150.00",
            market_value: "150.00",
            unrealized_pnl: "50.00",
            unrealized_pnl_pct: "50.00",
            stale: false,
          },
        ],
      },
    },
  });
  const client = new HttpFinkowClient({ baseUrl: "http://api.test", accountId: "acc-9" });
  const p = await client.getPortfolio();
  assert.equal(p.virtual, true);
  assert.equal(p.mode, "experimental");
  assert.equal(p.totalValueUsd, 1050);
  assert.equal(p.dayChangeUsd, 50);
  assert.equal(p.changeLabel, "all time");
  assert.equal(p.positions.length, 1);
  assert.equal(p.positions[0].label, "AAPL");
});

test("getOpportunities maps the radar response", async () => {
  mockFetch({
    "GET /api/radar/opportunities": {
      body: {
        opportunities: [{ symbol: "AAPL", score: 0.9, price: "150.00", reasoning: "Steady." }],
        provider: "stooq",
      },
    },
  });
  const client = new HttpFinkowClient({ baseUrl: "http://api.test" });
  const opps = await client.getOpportunities();
  assert.equal(opps.length, 1);
  assert.equal(opps[0].id, "AAPL");
  assert.ok(opps[0].summary.length > 0);
  assert.ok(opps[0].riskNote.length > 0);
});

test("getActivity maps backend events to feed items", async () => {
  mockFetch({
    "GET /api/agents/activity": {
      body: {
        events: [
          {
            id: "e1",
            agent: "radar",
            kind: "radar.scan.finished",
            payload: { symbols: 4 },
            created_at: "2026-10-16T09:41:00Z",
          },
        ],
      },
    },
  });
  const client = new HttpFinkowClient({ baseUrl: "http://api.test" });
  const events = await client.getActivity();
  assert.equal(events.length, 1);
  assert.equal(events[0].agent, "Radar");
  assert.ok(events[0].text.length > 0);
});

test("invest goes through the real order endpoint with a computed quantity", async () => {
  const calls = mockFetch({
    "GET /api/quotes/AAPL": {
      body: { symbol: "AAPL", price: "50.00", currency: "USD", provider: "stooq", stale: false },
    },
    "POST /api/orders": {
      body: {
        transaction_id: "txn-1",
        order_id: "ord-1",
        mode: "experimental",
        virtual: true,
        status: "filled",
        symbol: "AAPL",
      },
    },
  });
  const client = new HttpFinkowClient({ baseUrl: "http://api.test", accountId: "acc-9" });
  const result = await client.invest("AAPL", 100);
  const orderCall = calls.find((c) => c.url.endsWith("/api/orders"));
  assert.ok(orderCall, "posts the order to /api/orders");
  assert.equal(orderCall?.body?.account_id, "acc-9");
  assert.equal(orderCall?.body?.side, "buy");
  assert.equal(orderCall?.body?.quantity, "2");
  assert.ok(result.message.toLowerCase().includes("virtual"), "message labels virtual money");
});

test("requests work without a token (API dev-mode stays graceful)", async () => {
  const calls = mockFetch({ "GET /api/agents/activity": { body: { events: [] } } });
  const client = new HttpFinkowClient({ baseUrl: "http://api.test" });
  const events = await client.getActivity();
  assert.deepEqual(events, []);
  const headers = new Headers(calls[0].init?.headers as HeadersInit);
  assert.equal(headers.get("authorization"), null);
});

test("createFinkowClient http adapter reads env config", () => {
  process.env.NEXT_PUBLIC_FINKOW_ADAPTER = "http";
  process.env.NEXT_PUBLIC_FINKOW_API_URL = "http://backend:8000";
  try {
    const client = createFinkowClient();
    assert.ok(client instanceof HttpFinkowClient);
  } finally {
    delete process.env.NEXT_PUBLIC_FINKOW_ADAPTER;
    delete process.env.NEXT_PUBLIC_FINKOW_API_URL;
  }
});
