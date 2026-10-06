"use client";

import { ArrowRight, Sparkles } from "lucide-react";
import { useState } from "react";
import { PrimaryButton } from "./ui";

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
    <section aria-labelledby="goal-heading" className="reveal reveal-visible">
      <p className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-accent">
        <Sparkles className="h-3.5 w-3.5" aria-hidden />
        Your money, on autopilot
      </p>
      <h1
        id="goal-heading"
        className="max-w-2xl text-4xl font-semibold leading-tight tracking-tight sm:text-5xl"
      >
        What should your money do for you?
      </h1>
      <p className="mt-3 max-w-xl text-base leading-relaxed text-muted-foreground">
        Tell Finkow in plain words. Your agents build the plan, watch the market, and explain every
        move. No brokerage apps, no jargon.
      </p>

      <form onSubmit={submit} className="mt-6 max-w-2xl">
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
            className="w-full flex-1 rounded-xl border border-border bg-card px-5 py-3.5 text-base text-foreground placeholder:text-muted-foreground/60 transition-colors duration-200 focus:border-accent disabled:opacity-60"
          />
          <PrimaryButton type="submit" disabled={busy || !text.trim()} className="sm:w-auto">
            {busy ? "Planning…" : "Make a plan"}
            {!busy && <ArrowRight className="h-4 w-4" aria-hidden />}
          </PrimaryButton>
        </div>
      </form>

      <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label="Example goals">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            type="button"
            onClick={() => !busy && onSubmit(ex)}
            disabled={busy}
            className="cursor-pointer rounded-full border border-border bg-card px-4 py-1.5 text-sm text-muted-foreground transition-colors duration-200 hover:border-accent/60 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
          >
            {ex}
          </button>
        ))}
      </div>
    </section>
  );
}
