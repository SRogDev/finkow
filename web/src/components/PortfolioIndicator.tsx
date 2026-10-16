"use client";

import { ArrowDownRight, ArrowUpRight, Wallet } from "lucide-react";
import Link from "next/link";
import type { Portfolio } from "@/lib/finkow-client";
import { formatSignedUsd, formatUsd, TypingDots } from "./ui";

/**
 * Persistent portfolio indicator: current value, movement + direction,
 * and a link into the full portfolio view. Sits near the top of the
 * conversational workspace. Virtual capital is labeled every time.
 */
export function PortfolioIndicator({
  portfolio,
  loading,
  error,
}: {
  portfolio: Portfolio | null;
  loading: boolean;
  error: string | null;
}) {
  if (loading || (!portfolio && !error)) {
    return (
      <div
        className="flex items-center gap-3 rounded-2xl border border-border bg-card px-5 py-4"
        role="status"
        aria-label="Loading your portfolio"
      >
        <TypingDots label="Loading your portfolio" />
        <span className="text-sm text-muted-foreground">Checking your portfolio…</span>
      </div>
    );
  }

  if (error || !portfolio) {
    return (
      <div className="rounded-2xl border border-border bg-card px-5 py-4" role="alert">
        <p className="text-sm text-muted-foreground">
          Couldn&apos;t load your portfolio right now. {error ?? ""}
        </p>
      </div>
    );
  }

  const up = portfolio.dayChangeUsd >= 0;
  const changeLabel = portfolio.changeLabel ?? "today";
  const Arrow = up ? ArrowUpRight : ArrowDownRight;

  return (
    <Link
      href="/portfolio"
      aria-label={`Open portfolio view. Current value ${formatUsd(portfolio.totalValueUsd)}`}
      className="group flex cursor-pointer flex-wrap items-center justify-between gap-x-6 gap-y-3 rounded-2xl border border-border bg-card px-5 py-4 transition-colors duration-200 hover:border-accent/50 focus-visible:outline-2 focus-visible:outline-accent"
    >
      <div className="flex min-w-0 items-center gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent/10 text-accent">
          <Wallet className="h-5 w-5" aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Portfolio
            {portfolio.virtual !== false && (
              <span className="rounded-full border border-accent/40 bg-accent/10 px-2 py-0.5 text-[10px] font-semibold normal-case tracking-normal text-accent">
                Experimental · virtual
              </span>
            )}
          </p>
          <p className="tnum mt-0.5 truncate font-display text-3xl font-semibold tracking-tight text-foreground">
            {formatUsd(portfolio.totalValueUsd)}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <span
          className={`inline-flex items-center gap-1 text-sm font-semibold ${
            up ? "text-success" : "text-destructive"
          }`}
        >
          <Arrow className="h-4 w-4" aria-hidden />
          <span className="tnum">
            {formatSignedUsd(portfolio.dayChangeUsd)} ({up ? "+" : "−"}
            {Math.abs(portfolio.dayChangePct).toFixed(2)}%)
          </span>
        </span>
        <span className="text-xs text-muted-foreground">{changeLabel}</span>
        <span
          className="ml-1 text-xs font-medium text-accent opacity-0 transition-opacity duration-200 group-hover:opacity-100"
          aria-hidden
        >
          View →
        </span>
      </div>
    </Link>
  );
}
