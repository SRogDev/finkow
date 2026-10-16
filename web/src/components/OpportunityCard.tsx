"use client";

import { Check, ChevronDown, Info } from "lucide-react";
import { type ReactNode, useState } from "react";
import type { Opportunity } from "@/lib/finkow-client";
import { opportunitySections } from "@/lib/opportunity";
import { SpotlightCard } from "./effects";
import { formatUsd, GoldButton, Reveal } from "./ui";

/**
 * One opportunity, presented per the S16 contract: what was discovered,
 * why it may matter, the evidence, principal risks, whether any action
 * is proposed, and the next available action. Summary first; the full
 * analysis is one tap away (progressive disclosure). Never presented
 * as a guaranteed outcome; paper invests are always labeled virtual.
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
  const sections = opportunitySections(opportunity);
  const proposal = sections.proposedAction;

  const invest = async () => {
    if (busy || invested || !proposal) return;
    setBusy(true);
    try {
      const msg = await onInvest(opportunity.id, proposal.amountUsd);
      setMessage(msg);
    } catch {
      setMessage("Something went wrong — your paper money is safe. Try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Reveal delayMs={index * 80} className="reveal-visible h-full">
      <SpotlightCard className="h-full">
        <article className="flex h-full flex-col rounded-2xl border border-border bg-card p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-[0_16px_40px_-16px_rgba(245,158,11,0.25)]">
          <div className="flex items-center justify-between gap-3">
            <span className="rounded-full border border-accent/30 bg-accent/10 px-2.5 py-1 text-xs font-semibold text-gold-light">
              {opportunity.category}
            </span>
            {invested ? (
              <span className="inline-flex items-center gap-1 text-xs font-medium text-success">
                <Check className="h-3.5 w-3.5" aria-hidden />
                You&apos;re in
              </span>
            ) : (
              <span className="rounded-full border border-border px-2.5 py-1 text-[11px] font-medium text-muted-foreground">
                Virtual money
              </span>
            )}
          </div>

          <h3 className="mt-3 text-lg font-semibold tracking-tight text-foreground">
            {opportunity.title}
          </h3>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            {sections.discovered}
          </p>

          {proposal && (
            <div className="mt-4 rounded-xl border border-accent/30 bg-accent/10 px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.12em] text-accent">
                Finkow proposes
              </p>
              <p className="tnum mt-1 text-base font-semibold text-foreground">
                {formatUsd(proposal.amountUsd)}{" "}
                <span className="text-xs font-medium text-muted-foreground">virtual</span>
              </p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                {proposal.rationale}
              </p>
            </div>
          )}

          <details className="why-details group mt-4">
            <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 text-sm font-medium text-accent transition-colors duration-200 hover:brightness-110 [&::-webkit-details-marker]:hidden">
              <ChevronDown
                className="h-4 w-4 transition-transform duration-200 group-open:rotate-180"
                aria-hidden
              />
              Full analysis
            </summary>
            <div className="mt-4 space-y-4">
              <AnalysisBlock title="Why this may matter">
                <ul className="space-y-2">
                  {sections.whyItMatters.map((point) => (
                    <li
                      key={point}
                      className="flex items-start gap-2 text-sm leading-relaxed text-foreground/90"
                    >
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />
                      <span>{point}</span>
                    </li>
                  ))}
                </ul>
              </AnalysisBlock>

              <AnalysisBlock title="Supporting evidence">
                {sections.evidence.length > 0 ? (
                  <ul className="space-y-2">
                    {sections.evidence.map((point) => (
                      <li
                        key={point}
                        className="flex items-start gap-2 text-sm leading-relaxed text-foreground/90"
                      >
                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />
                        <span>{point}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    Your agents haven&apos;t logged supporting evidence for this one yet.
                  </p>
                )}
              </AnalysisBlock>

              <AnalysisBlock title="Principal risks">
                <ul className="space-y-2">
                  {sections.risks.map((risk) => (
                    <li
                      key={risk}
                      className="flex items-start gap-2 text-sm leading-relaxed text-foreground/90"
                    >
                      <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                      <span>{risk}</span>
                    </li>
                  ))}
                </ul>
              </AnalysisBlock>

              <AnalysisBlock title="What happens next">
                <p className="text-sm leading-relaxed text-foreground/90">{sections.nextAction}</p>
              </AnalysisBlock>
            </div>
          </details>

          <div className="mt-5 flex-1" />
          <div>
            {message ? (
              <p className="text-sm font-medium text-success" role="status">
                {message}
              </p>
            ) : (
              proposal && (
                <GoldButton onClick={invest} disabled={busy || invested} className="w-full">
                  {busy
                    ? "Investing…"
                    : invested
                      ? "Invested"
                      : `Invest ${formatUsd(proposal.amountUsd)} (paper money)`}
                </GoldButton>
              )
            )}
            <p className="mt-2 text-center text-xs text-muted-foreground">
              One tap places a virtual order. No real money moves — ever.
            </p>
          </div>
        </article>
      </SpotlightCard>
    </Reveal>
  );
}

function AnalysisBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        {title}
      </h4>
      {children}
    </div>
  );
}
