"use client";

import { ArrowRight, Sparkles } from "lucide-react";
import { useState } from "react";
import { LampGlow } from "./effects";
import { GoldButton } from "./ui";

const EXAMPLES = [
  "Grow $1,000 over 5 years, low risk",
  "Save for a big trip next year",
  "Build long-term wealth — I can handle ups and downs",
];

export function GoalInput({ onSubmit, busy }: { onSubmit: (text: string) => void; busy: boolean }) {
  const [text, setText] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (text.trim() && !busy) onSubmit(text.trim());
  };

  return (
    <section aria-labelledby="goal-heading" className="reveal reveal-visible relative">
      <LampGlow />
      <div className="relative">
        <p className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-accent">
          <Sparkles className="h-3.5 w-3.5" aria-hidden />
          Your money, on autopilot
        </p>
        <h1
          id="goal-heading"
          className="max-w-2xl font-display text-5xl font-semibold leading-[1.05] tracking-tight sm:text-6xl"
        >
          What should your <span className="gold-text">money</span> do for you?
        </h1>
        <p className="mt-4 max-w-xl text-base leading-relaxed text-muted-foreground">
          Tell Finkow in plain words. Your agents build the plan, watch the market, and explain
          every move. No brokerage apps, no jargon.
        </p>

        <form onSubmit={submit} className="mt-7 max-w-2xl">
          <label htmlFor="goal-input" className="sr-only">
            Describe your financial goal
          </label>
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              id="goal-input"
              type="text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="e.g. Grow $1,000 over 5 years, low risk"
              disabled={busy}
              className="w-full flex-1 rounded-xl border border-border bg-card/80 px-5 py-3.5 text-base text-foreground shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] backdrop-blur placeholder:text-muted-foreground/60 transition-all duration-200 focus:border-accent focus:shadow-[0_0_0_3px_rgba(245,158,11,0.18)] focus:outline-none disabled:opacity-60"
            />
            <GoldButton type="submit" disabled={busy || !text.trim()} className="sm:w-auto">
              {busy ? "Planning…" : "Make a plan"}
              {!busy && <ArrowRight className="h-4 w-4" aria-hidden />}
            </GoldButton>
          </div>
        </form>

        <fieldset className="mt-4 flex flex-wrap gap-2" aria-label="Example goals">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => !busy && onSubmit(ex)}
              disabled={busy}
              className="cursor-pointer rounded-full border border-border bg-card/80 px-4 py-1.5 text-sm text-muted-foreground backdrop-blur transition-all duration-200 hover:border-accent/60 hover:text-gold-light disabled:cursor-not-allowed disabled:opacity-50"
            >
              {ex}
            </button>
          ))}
        </fieldset>
      </div>
    </section>
  );
}
