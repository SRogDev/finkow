"use client";

import type { Portfolio } from "@/lib/finkow-client";
import { GoldRule } from "./effects";
import { Card, formatSignedUsd, formatUsd, LiveDot, SectionHeading, TypingDots } from "./ui";

/**
 * Portfolio pulse: the portfolio as a living thing, in plain language.
 * Deliberately not a spreadsheet — one status, one number, one sentence.
 * The number glows like gold in the mine: gradient text over a breathing aura.
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
    <Card className="relative overflow-hidden">
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

          <div className="relative mt-4">
            <div
              className="gold-ambient pointer-events-none absolute -inset-6 rounded-full bg-[radial-gradient(ellipse_at_center,rgba(245,158,11,0.16),transparent_70%)] blur-2xl"
              aria-hidden
            />
            <p className="tnum gold-text relative font-display text-6xl font-semibold tracking-tight">
              {formatUsd(portfolio.totalValueUsd)}
            </p>
          </div>
          <p
            className={`tnum mt-2 text-sm font-medium ${up ? "text-success" : "text-destructive"}`}
          >
            {formatSignedUsd(portfolio.dayChangeUsd)} today ({up ? "+" : "−"}
            {Math.abs(portfolio.dayChangePct).toFixed(1)}%)
          </p>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-muted-foreground">
            {portfolio.pulseDetail}
          </p>

          <GoldRule className="my-5" />

          <div className="space-y-3">
            {portfolio.positions.map((pos) => (
              <div key={pos.id} className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground">{pos.label}</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{pos.note}</p>
                </div>
                <p className="tnum shrink-0 text-sm font-semibold text-gold-light">
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
