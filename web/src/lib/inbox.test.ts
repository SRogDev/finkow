import assert from "node:assert/strict";
import { test } from "node:test";
import type { ActivityEvent, AuditEntry, Order } from "./api.ts";
import {
  activityToInbox,
  auditToInbox,
  type InboxItem,
  mergeInbox,
  ordersToInbox,
} from "./inbox.ts";

function order(overrides: Partial<Order> = {}): Order {
  return {
    order_id: "ord-1",
    account_id: "acc-1",
    mode: "experimental",
    virtual: true,
    symbol: "AAPL",
    side: "buy",
    quantity: "10",
    status: "filled",
    filled_qty: "10",
    avg_fill_price: "150.00",
    provider_order_id: null,
    simulated: true,
    reject_reason: null,
    created_at: "2026-10-16T10:00:00Z",
    updated_at: "2026-10-16T10:00:05Z",
    ...overrides,
  };
}

test("orders awaiting authorization need attention", () => {
  const [item] = ordersToInbox([order({ status: "awaiting_authorization" })]);
  assert.equal(item.state, "attention");
  assert.ok(item.nextAction, "attention items always name a next action");
  assert.ok(item.why.length > 0, "items explain why");
  assert.ok(item.title.includes("AAPL"));
});

test("submitted orders are in progress, filled orders are completed", () => {
  const [sub] = ordersToInbox([order({ status: "submitted" })]);
  const [part] = ordersToInbox([order({ status: "partially_filled" })]);
  const [filled] = ordersToInbox([order({ status: "filled" })]);
  const [rejected] = ordersToInbox([order({ status: "rejected", reject_reason: "risk limit" })]);
  assert.equal(sub.state, "in-progress");
  assert.equal(part.state, "in-progress");
  assert.equal(filled.state, "completed");
  assert.equal(rejected.state, "completed");
  assert.ok(rejected.why.includes("risk limit"), "reject reason is surfaced honestly");
});

test("order items carry the virtual flag, never implying real execution", () => {
  const [virtualItem] = ordersToInbox([order({ virtual: true, simulated: true })]);
  assert.equal(virtualItem.virtual, true);
  assert.ok(virtualItem.statusLabel.length > 0);
});

test("activity events map by kind, defaulting to completed", () => {
  const evt = (kind: string): ActivityEvent => ({
    id: `e-${kind}`,
    agent: "radar",
    kind,
    payload: { symbol: "AAPL", score: 0.9 },
    created_at: "2026-10-16T09:00:00Z",
  });
  const [propose] = activityToInbox([evt("order.proposed")]);
  const [submit] = activityToInbox([evt("order.submitted")]);
  const [done] = activityToInbox([evt("radar.scan.finished")]);
  assert.equal(propose.state, "attention");
  assert.equal(submit.state, "in-progress");
  assert.equal(done.state, "completed");
  assert.ok(done.title.length > 0 && done.why.length > 0);
});

test("audit failures need attention, successes complete", () => {
  const entry = (outcome: string): AuditEntry => ({
    id: `a-${outcome}`,
    actor: "executor",
    action: "order.place",
    account_id: "acc-1",
    outcome,
    details: { reason: "insufficient funds" },
    created_at: "2026-10-16T08:00:00Z",
  });
  const [failed] = auditToInbox([entry("failed")]);
  const [denied] = auditToInbox([entry("denied")]);
  const [ok] = auditToInbox([entry("ok")]);
  assert.equal(failed.state, "attention");
  assert.equal(denied.state, "attention");
  assert.equal(ok.state, "completed");
  assert.ok(failed.why.includes("insufficient funds"));
});

test("mergeInbox sorts newest first and keeps every item", () => {
  const items: InboxItem[] = [
    {
      id: "old",
      state: "completed",
      title: "old",
      why: "old",
      statusLabel: "done",
      nextAction: null,
      at: "2026-10-15T10:00:00Z",
      source: "audit",
      virtual: false,
    },
    {
      id: "new",
      state: "attention",
      title: "new",
      why: "new",
      statusLabel: "waiting",
      nextAction: "act",
      at: "2026-10-16T10:00:00Z",
      source: "order",
      virtual: true,
    },
  ];
  const merged = mergeInbox(items);
  assert.equal(merged.length, 2);
  assert.equal(merged[0].id, "new");
  assert.equal(merged[1].id, "old");
});

test("unknown order statuses surface honestly instead of being hidden", () => {
  const [item] = ordersToInbox([order({ status: "mystery_status" })]);
  assert.equal(item.state, "completed");
  assert.ok(item.statusLabel.toLowerCase().includes("mystery"), "raw status still visible");
});
