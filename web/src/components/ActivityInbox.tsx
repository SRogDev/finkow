"use client";

import { Activity, ArrowLeftRight, Inbox, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError, getActivity, getAudit, getOrCreateAccountId, getOrders } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  activityToInbox,
  auditToInbox,
  type InboxItem,
  type InboxState,
  mergeInbox,
  ordersToInbox,
} from "@/lib/inbox";
import { Card, SectionHeading, TypingDots } from "./ui";

const TABS: { id: InboxState; label: string }[] = [
  { id: "attention", label: "Needs attention" },
  { id: "in-progress", label: "In progress" },
  { id: "completed", label: "Completed" },
];

const SOURCE_META = {
  order: { icon: ArrowLeftRight, label: "Order" },
  activity: { icon: Activity, label: "Activity" },
  audit: { icon: ShieldCheck, label: "Audit" },
} as const;

const STATE_STYLES: Record<InboxState, string> = {
  attention: "border-accent/50 bg-accent/10 text-accent",
  "in-progress": "border-border bg-muted text-foreground",
  completed: "border-border bg-transparent text-muted-foreground",
};

/**
 * Activity Inbox: one honest queue with three states, fed by the real
 * activity/audit/order endpoints. Every item says what happened, why,
 * its status, and the next action — under one Finkow identity.
 * Never fabricates: with no backend, it says so instead of inventing rows.
 */
export function ActivityInbox() {
  const [items, setItems] = useState<InboxItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<InboxState>("attention");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const accountId = await getOrCreateAccountId();
        // Independent reads — one slow source must not block the others.
        const [orders, events, entries] = await Promise.all([
          getOrders(accountId),
          getActivity(),
          getAudit(accountId),
        ]);
        if (cancelled) return;
        setItems(
          mergeInbox([
            ...ordersToInbox(orders),
            ...activityToInbox(events),
            ...auditToInbox(entries),
          ]),
        );
        setError(null);
      } catch (e) {
        if (cancelled) return;
        setError(
          e instanceof ApiError
            ? e.detail
            : "Couldn't reach the Finkow API. Start the backend to see live activity here.",
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const counts: Record<InboxState, number> = {
    attention: 0,
    "in-progress": 0,
    completed: 0,
  };
  for (const item of items) counts[item.state] += 1;
  const shown = items.filter((i) => i.state === tab);

  return (
    <Card>
      <SectionHeading
        eyebrow="Finkow at work"
        title="Activity inbox"
        hint="Everything Finkow does, in one queue. Nothing moves without its reasoning attached."
      />

      {loading ? (
        <div className="py-6" role="status" aria-label="Loading activity">
          <TypingDots label="Loading activity" />
        </div>
      ) : error ? (
        <div
          className="flex items-start gap-3 rounded-xl border border-border bg-background px-4 py-5"
          role="alert"
        >
          <Inbox className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" aria-hidden />
          <div>
            <p className="text-sm font-medium text-foreground">No live activity yet</p>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{error}</p>
          </div>
        </div>
      ) : (
        <div>
          <div className="flex gap-2" role="tablist" aria-label="Activity states">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                onClick={() => setTab(t.id)}
                className={`cursor-pointer rounded-full border px-4 py-1.5 text-sm font-medium transition-colors duration-200 ${
                  tab === t.id
                    ? "border-accent/60 bg-accent/10 text-accent"
                    : "border-border text-muted-foreground hover:border-accent/40 hover:text-foreground"
                }`}
              >
                {t.label}
                <span className="tnum ml-1.5 text-xs opacity-70">{counts[t.id]}</span>
              </button>
            ))}
          </div>

          {shown.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Nothing here right now.
            </p>
          ) : (
            <ol className="mt-4 space-y-3" aria-live="polite">
              {shown.map((item) => (
                <InboxRow key={item.id} item={item} />
              ))}
            </ol>
          )}
        </div>
      )}
    </Card>
  );
}

function InboxRow({ item }: { item: InboxItem }) {
  const meta = SOURCE_META[item.source];
  const Icon = meta.icon;
  return (
    <li className={`rounded-xl border px-4 py-3.5 ${STATE_STYLES[item.state]}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Icon className="h-3.5 w-3.5" aria-hidden />
          {meta.label}
        </span>
        <span className="rounded-full border border-current px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide opacity-80">
          {item.statusLabel}
        </span>
        {item.virtual && (
          <span className="rounded-full border border-accent/40 bg-accent/10 px-2 py-0.5 text-[11px] font-medium text-accent">
            Virtual
          </span>
        )}
        <span className="ml-auto text-xs text-muted-foreground">{formatDateTime(item.at)}</span>
      </div>
      <p className="mt-2 text-sm font-semibold text-foreground">{item.title}</p>
      <p className="mt-1 line-clamp-4 text-sm leading-relaxed text-muted-foreground">{item.why}</p>
      {item.nextAction && (
        <p className="mt-2 text-sm font-medium text-accent">
          <span className="font-semibold">Next:</span> {item.nextAction}
        </p>
      )}
    </li>
  );
}
