"use client";

import { useEffect, useMemo, useState } from "react";
import { AgentFeed } from "@/components/AgentFeed";
import { Explainer } from "@/components/Explainer";
import { InfiniteRail } from "@/components/effects";
import { GoalInput } from "@/components/GoalInput";
import { OpportunityCard } from "@/components/OpportunityCard";
import { PlanCard } from "@/components/PlanCard";
import { PortfolioPulse } from "@/components/PortfolioPulse";
import { SectionHeading } from "@/components/ui";
import {
  type AgentEvent,
  createFinkowClient,
  type Opportunity,
  type Plan,
  type Portfolio,
} from "@/lib/finkow-client";

/**
 * Finkow v2 home: one conversational surface.
 * Goal in → plan out → agents work → opportunities → explanations.
 * No tickers, no order forms, no brokerage screens.
 *
 * Client component: the whole surface is interactive (forms, live feed,
 * invest actions). The server gate in app/page.tsx decides whether this
 * renders at all — nothing non-serializable crosses that boundary.
 */
export function HomeApp() {
  const client = useMemo(() => createFinkowClient(), []);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [activity, setActivity] = useState<AgentEvent[]>([]);
  const [booting, setBooting] = useState(true);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [planning, setPlanning] = useState(false);
  const [investedIds, setInvestedIds] = useState<ReadonlySet<string>>(new Set());
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([client.getPortfolio(), client.getOpportunities(), client.getActivity()])
      .then(([p, opps, events]) => {
        if (cancelled) return;
        setPortfolio(p);
        setOpportunities(opps);
        setActivity(events);
      })
      .catch(() => {
        /* The feed and pulse render their own loading states; a total
           failure still leaves the goal input usable. */
      })
      .finally(() => {
        if (!cancelled) setBooting(false);
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  const submitGoal = async (text: string) => {
    setPlanning(true);
    try {
      const goal = await client.createGoal(text);
      // Independent once the goal exists — fetch in parallel, not in sequence.
      const [nextPlan, events] = await Promise.all([client.getPlan(goal.id), client.getActivity()]);
      setPlan(nextPlan);
      setActivity(events);
    } finally {
      setPlanning(false);
    }
  };

  const invest = async (opportunityId: string, amountUsd: number): Promise<string> => {
    const result = await client.invest(opportunityId, amountUsd);
    const [p, events] = await Promise.all([client.getPortfolio(), client.getActivity()]);
    setPortfolio(p);
    setActivity(events);
    setInvestedIds((prev) => new Set(prev).add(opportunityId));
    return result.message;
  };

  return (
    <div className={`flex flex-col gap-10 ${mounted ? "reveal-visible" : ""}`}>
      <GoalInput onSubmit={submitGoal} busy={planning} />

      {(plan || planning) && (
        <div aria-live="polite">
          {planning && !plan ? <PlanSkeleton /> : plan && <PlanCard plan={plan} />}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <PortfolioPulse portfolio={portfolio} loading={booting} />
        <AgentFeed events={activity} />
      </div>

      <section aria-labelledby="opps-heading">
        <div id="opps-heading">
          <SectionHeading
            eyebrow="Opportunity radar"
            title="What your agents see right now"
            hint="Hand-picked for a calm, long-term plan. One tap puts paper money to work. Hover to pause the rail."
          />
        </div>
        {opportunities.length === 0 ? (
          <div className="grid gap-4 sm:grid-cols-2">
            {[0, 1].map((i) => (
              <div key={i} className="shimmer h-64 rounded-2xl" aria-hidden />
            ))}
          </div>
        ) : (
          <InfiniteRail label="Opportunity rail" className="-mx-4 px-4 sm:-mx-6 sm:px-6">
            {opportunities.map((opp, i) => (
              <OpportunityCard
                key={opp.id}
                opportunity={opp}
                onInvest={invest}
                invested={investedIds.has(opp.id)}
                index={i}
              />
            ))}
          </InfiniteRail>
        )}
      </section>

      <Explainer client={client} />
    </div>
  );
}

function PlanSkeleton() {
  return (
    <div
      className="rounded-2xl border border-border bg-card p-6"
      role="status"
      aria-label="Building your plan"
    >
      <div className="shimmer h-5 w-40 rounded" />
      <div className="shimmer mt-4 h-4 w-full rounded" />
      <div className="shimmer mt-2 h-4 w-5/6 rounded" />
      <div className="shimmer mt-6 h-2 w-full rounded-full" />
      <div className="shimmer mt-4 h-2 w-full rounded-full" />
    </div>
  );
}
