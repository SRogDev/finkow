"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ActivityInbox } from "@/components/ActivityInbox";
import { Explainer } from "@/components/Explainer";
import { ScrollRail } from "@/components/effects";
import { GoalInput } from "@/components/GoalInput";
import { OpportunityCard } from "@/components/OpportunityCard";
import { PlanCard } from "@/components/PlanCard";
import { PortfolioIndicator } from "@/components/PortfolioIndicator";
import { ErrorState, SectionHeading } from "@/components/ui";
import { getStoredAccountId } from "@/lib/api";
import { getAccessToken } from "@/lib/auth/token";
import {
  createFinkowClient,
  type Opportunity,
  type Plan,
  type Portfolio,
} from "@/lib/finkow-client";

const EXPLORE_SYMBOLS = ["AAPL", "MSFT", "BTC", "ETH"];

/**
 * Finkow home: a conversational workspace, not a dashboard.
 * Portfolio indicator → natural-language input → plan → activity inbox →
 * discoveries → ask why. No tickers, no order forms, no brokerage screens.
 *
 * Client component: the whole surface is interactive (forms, invest
 * actions). The server gate in app/page.tsx decides whether this renders
 * at all — nothing non-serializable crosses that boundary.
 */
export function HomeApp() {
  // Sync, no network: the sandbox account id when this browser has one.
  const [accountId] = useState<string | null>(() => getStoredAccountId());
  const client = useMemo(
    () =>
      createFinkowClient({
        accountId: accountId ?? undefined,
        getToken: getAccessToken,
      }),
    [accountId],
  );
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [booting, setBooting] = useState(true);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [planning, setPlanning] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const [lastGoal, setLastGoal] = useState<string | null>(null);
  const [investedIds, setInvestedIds] = useState<ReadonlySet<string>>(new Set());
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    let cancelled = false;
    // Independent reads — one slow source must not block the others.
    Promise.allSettled([client.getPortfolio(), client.getOpportunities()]).then((results) => {
      if (cancelled) return;
      const [p, opps] = results;
      if (p.status === "fulfilled") {
        setPortfolio(p.value);
      } else {
        setPortfolioError("Your portfolio couldn't be loaded.");
      }
      if (opps.status === "fulfilled") setOpportunities(opps.value);
      setBooting(false);
    });
    return () => {
      cancelled = true;
    };
  }, [client]);

  const submitGoal = async (text: string) => {
    setPlanning(true);
    setPlanError(null);
    setPlan(null);
    setLastGoal(text);
    try {
      const goal = await client.createGoal(text);
      setPlan(await client.getPlan(goal.id));
    } catch {
      setPlanError("Couldn't build your plan right now. Your words are safe — try again.");
    } finally {
      setPlanning(false);
    }
  };

  const invest = async (opportunityId: string, amountUsd: number): Promise<string> => {
    const result = await client.invest(opportunityId, amountUsd);
    const p = await client.getPortfolio();
    setPortfolio(p);
    setInvestedIds((prev) => new Set(prev).add(opportunityId));
    return result.message;
  };

  return (
    <div className={`flex flex-col gap-10 ${mounted ? "reveal-visible" : ""}`}>
      <PortfolioIndicator portfolio={portfolio} loading={booting} error={portfolioError} />

      <GoalInput onSubmit={submitGoal} busy={planning} />

      {(plan || planning || planError) && (
        <div aria-live="polite">
          {planning && !plan ? (
            <PlanSkeleton />
          ) : plan ? (
            <PlanCard plan={plan} />
          ) : planError ? (
            <ErrorState
              message={planError}
              onRetry={lastGoal ? () => submitGoal(lastGoal) : undefined}
            />
          ) : null}
        </div>
      )}

      <ActivityInbox />

      <section aria-labelledby="opps-heading">
        <div id="opps-heading">
          <SectionHeading
            eyebrow="Opportunity radar"
            title="What Finkow sees right now"
            hint="Hand-picked for a calm, long-term plan. One tap puts virtual money to work."
          />
        </div>
        {booting ? (
          <div className="grid gap-4 sm:grid-cols-2" aria-hidden>
            {[0, 1].map((i) => (
              <div key={i} className="shimmer h-64 rounded-2xl" />
            ))}
          </div>
        ) : opportunities.length === 0 ? (
          <p className="rounded-2xl border border-border bg-card px-6 py-8 text-center text-sm text-muted-foreground">
            No opportunities right now. Finkow will surface them here when they appear.
          </p>
        ) : (
          <ScrollRail label="Opportunity rail" className="-mx-4 px-4 sm:-mx-6 sm:px-6">
            {opportunities.map((opp, i) => (
              <OpportunityCard
                key={opp.id}
                opportunity={opp}
                onInvest={invest}
                invested={investedIds.has(opp.id)}
                index={i}
              />
            ))}
          </ScrollRail>
        )}
      </section>

      <Explainer client={client} />

      <nav aria-label="Explore" className="flex flex-wrap items-center gap-2">
        <Link
          href="/portfolio"
          className="inline-flex cursor-pointer items-center rounded-full border border-accent/40 bg-accent/10 px-4 py-1.5 text-sm font-medium text-accent transition-colors duration-200 hover:bg-accent/20"
        >
          Portfolio
        </Link>
        {EXPLORE_SYMBOLS.map((symbol) => (
          <Link
            key={symbol}
            href={`/assets/${symbol}`}
            className="inline-flex cursor-pointer items-center rounded-full border border-border px-4 py-1.5 text-sm font-medium text-muted-foreground transition-colors duration-200 hover:border-accent/40 hover:text-foreground"
          >
            {symbol}
          </Link>
        ))}
      </nav>
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
