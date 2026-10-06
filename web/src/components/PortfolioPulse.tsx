"use client";

import type { Portfolio } from "@/lib/finkow-client";
import { Card, formatSignedUsd, formatUsd, LiveDot, SectionHeading, TypingDots } from "./ui";

/**
 * Portfolio pulse: the portfolio as a living thing, in plain language.
 * Deliberately not a spreadsheet — one status, one number, one sentence.
 */
export function PortfolioPulse({
  portfolio,
  loading,
}: {
  portfolio: Portfolio | null;
  loading: boolean;
}) {
  const up = (portfolio?.dayChangeUsd ?? 0) >= 0;

  return (
    <Card>
      <SectionHeading
        eyebrow="Portfolio pulse"
        title="How your money is doing"
        hint="Paper money while you learn. Real investing comes later."
      />

      {loading || !portfolio ? (
        <div className="py-6" role="status" aria-label="Loading your portfolio">
          <TypingDots label="Checking your portfolio" />
        </div>
      ) : (
        <div aria-live="polite">
          <div className="flex items-center gap-2.5">
            <LiveDot />
            <p className="text-sm font-medium text-foreground">{portfolio.pulseText}</p>
          </div>

          <p className="tnum mt-4 text-5xl font-semibold tracking-tight text-foreground">
            {formatUsd(portfolio.totalValueUsd)}
          </p>
          <p
            className={`tnum mt-2 text-sm font-medium ${up ? "text-success" : "text-destructive"}`}
          >
            {formatSignedUsd(portfolio.dayChangeUsd)} today ({up ? "+" : "−"}
            {Math.abs(portfolio.dayChangePct).toFixed(1)}%)
          </p>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-muted-foreground">
            {portfolio.pulseDetail}
          </p>

          <div className="mt-6 space-y-3 border-t border-border pt-5">
            {portfolio.positions.map((pos) => (
              <div key={pos.id} className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground">{pos.label}</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{pos.note}</p>
                </div>
                <p className="tnum shrink-0 text-sm font-semibold text-foreground">
                  {formatUsd(pos.valueUsd)}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
