"use client";

import { Check } from "lucide-react";
import { useState } from "react";
import type { Opportunity } from "@/lib/finkow-client";
import { formatUsd, PrimaryButton, Reveal, WhyDetails } from "./ui";

/**
 * One opportunity, in plain language, with one-tap paper investing.
 * No tickers, no order forms — the agent handles the how.
 */
export function OpportunityCard({
  opportunity,
  onInvest,
  invested,
  index,
}: {
  opportunity: Opportunity;
  onInvest: (opportunityId: string, amountUsd: number) => Promise<string>;
  invested: boolean;
  index: number;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const invest = async () => {
    if (busy || invested) return;
    setBusy(true);
    try {
      const msg = await onInvest(opportunity.id, 100);
      setMessage(msg);
    } catch {
      setMessage("Something went wrong — your paper money is safe. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Reveal delayMs={index * 80} className="reveal-visible">
      <article className="flex h-full flex-col rounded-2xl border border-border bg-card p-6 transition-colors duration-200 hover:border-accent/40">
        <div className="flex items-center justify-between gap-3">
          <span className="rounded-full bg-accent/10 px-2.5 py-1 text-xs font-semibold text-accent">
            {opportunity.category}
          </span>
          {invested && (
            <span className="inline-flex items-center gap-1 text-xs font-medium text-success">
              <Check className="h-3.5 w-3.5" aria-hidden />
              You're in
            </span>
          )}
        </div>

        <h3 className="mt-3 text-lg font-semibold tracking-tight text-foreground">
          {opportunity.title}
        </h3>
        <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">
          {opportunity.summary}
        </p>

        <WhyDetails points={opportunity.why} riskNote={opportunity.riskNote} />

        <div className="mt-5">
          {message ? (
            <p className="text-sm font-medium text-success" role="status">
              {message}
            </p>
          ) : (
            <PrimaryButton onClick={invest} disabled={busy || invested} className="w-full">
              {busy ? "Investing…" : invested ? "Invested" : `Invest ${formatUsd(100)} (paper)`}
            </PrimaryButton>
          )}
          <p className="mt-2 text-center text-xs text-muted-foreground">
            One tap. Your Pilot agent handles the rest.
          </p>
        </div>
      </article>
    </Reveal>
  );
}
