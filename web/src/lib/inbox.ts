/**
 * Activity Inbox mapping: the real backend surfaces activity events, audit
 * entries, and orders in different shapes. This module turns them into one
 * honest inbox with three states — requires attention, in progress,
 * completed — under a single Finkow identity (never organized by agent
 * names). Pure functions, unit-tested. No invented reasons: every "why"
 * comes from the record itself.
 */
import type { ActivityEvent, AuditEntry, Order } from "./api.ts";

export type InboxState = "attention" | "in-progress" | "completed";

export interface InboxItem {
  id: string;
  state: InboxState;
  /** What happened. */
  title: string;
  /** Why it matters / what it means. */
  why: string;
  /** Human status label. */
  statusLabel: string;
  /** The next action for the human, or null when there is none. */
  nextAction: string | null;
  /** ISO timestamp. */
  at: string;
  source: "order" | "activity" | "audit";
  /** True when the underlying money is virtual (experimental mode). */
  virtual: boolean;
}

function humanize(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/\./g, " · ").trim();
}

function capitalize(value: string): string {
  return value.length === 0 ? value : value[0].toUpperCase() + value.slice(1);
}

/** Short honest summary of a JSON payload: "symbol: AAPL, score: 0.9". */
function payloadSummary(payload: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(payload ?? {})) {
    if (parts.length >= 3) break;
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      parts.push(`${humanize(key)}: ${value}`);
    }
  }
  return parts.join(", ");
}

/* ------------------------------------------------------------------ */
/* Orders                                                              */
/* ------------------------------------------------------------------ */

export function ordersToInbox(orders: Order[]): InboxItem[] {
  return orders.map((o) => {
    const status = o.status.toLowerCase();
    let state: InboxState = "completed";
    let nextAction: string | null = null;
    if (status === "draft" || status === "awaiting_authorization") {
      state = "attention";
      nextAction = "This order needs your approval before it can be submitted.";
    } else if (status === "submitted" || status === "partially_filled") {
      state = "in-progress";
    }

    const sideWord = o.side === "buy" ? "Buy" : "Sell";
    const title = `${sideWord} ${o.quantity} ${o.symbol}`;
    let why: string;
    if (o.reject_reason) {
      why = `Rejected: ${o.reject_reason}`;
    } else if (status === "filled") {
      why =
        `Filled ${o.filled_qty} at an average of ${o.avg_fill_price ?? "—"}. ` +
        (o.simulated ? "Simulated fill — virtual money only." : "");
    } else if (state === "attention") {
      why = "The order is drafted and waiting for a human decision.";
    } else if (state === "in-progress") {
      why = `The order is ${humanize(o.status)} — Finkow is working on it.`;
    } else {
      why = `Order ended as ${humanize(o.status)}.`;
    }

    return {
      id: `order-${o.order_id}`,
      state,
      title,
      why: why.trim(),
      statusLabel: capitalize(humanize(o.status)),
      nextAction,
      at: o.updated_at || o.created_at,
      source: "order",
      virtual: o.virtual,
    };
  });
}

/* ------------------------------------------------------------------ */
/* Agent activity events                                               */
/* ------------------------------------------------------------------ */

const ATTENTION_KINDS = ["propos", "await", "approval", "alert", "action_required", "attention"];
const PROGRESS_KINDS = ["submit", "progress", "reconcil", "start", "execut"];

function kindState(kind: string): InboxState {
  const k = kind.toLowerCase();
  if (ATTENTION_KINDS.some((w) => k.includes(w))) return "attention";
  if (PROGRESS_KINDS.some((w) => k.includes(w))) return "in-progress";
  return "completed";
}

export function activityToInbox(events: ActivityEvent[]): InboxItem[] {
  return events.map((e) => {
    const state = kindState(e.kind);
    const summary = payloadSummary(e.payload);
    return {
      id: `activity-${e.id}`,
      state,
      title: capitalize(humanize(e.kind)),
      why: summary || `Recorded by Finkow at ${e.created_at}.`,
      statusLabel: capitalize(humanize(e.kind)),
      nextAction:
        state === "attention" ? "This needs your decision — nothing moves until you decide." : null,
      at: e.created_at,
      source: "activity",
      virtual: (e.payload?.virtual as boolean | undefined) === true,
    };
  });
}

/* ------------------------------------------------------------------ */
/* Audit entries                                                       */
/* ------------------------------------------------------------------ */

const ATTENTION_OUTCOMES = ["failed", "denied", "error", "rejected"];
const PROGRESS_OUTCOMES = ["pending", "started", "in_progress"];

function outcomeState(outcome: string): InboxState {
  const o = outcome.toLowerCase();
  if (ATTENTION_OUTCOMES.includes(o)) return "attention";
  if (PROGRESS_OUTCOMES.includes(o)) return "in-progress";
  return "completed";
}

export function auditToInbox(entries: AuditEntry[]): InboxItem[] {
  return entries.map((e) => {
    const state = outcomeState(e.outcome);
    const summary = payloadSummary(e.details);
    return {
      id: `audit-${e.id}`,
      state,
      title: `${capitalize(humanize(e.action))} — ${humanize(e.outcome)}`,
      why: summary || `Recorded in the audit log at ${e.created_at}.`,
      statusLabel: capitalize(humanize(e.outcome)),
      nextAction:
        state === "attention"
          ? "Check what failed and decide whether anything needs fixing."
          : null,
      at: e.created_at,
      source: "audit",
      virtual: false,
    };
  });
}

/* ------------------------------------------------------------------ */

export function mergeInbox(items: InboxItem[]): InboxItem[] {
  return [...items].sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
}
