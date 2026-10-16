"use client";

import { useState } from "react";
import type { Explanation, FinkowClient } from "@/lib/finkow-client";
import { Card, GhostButton, PrimaryButton, SectionHeading, TypingDots } from "./ui";

const PRESET_QUESTION = "Why did my portfolio move today?";

/**
 * "Ask why" — grounded explanations in plain language.
 * Every answer cites the facts it stands on. No black-box moves.
 */
export function Explainer({ client }: { client: FinkowClient }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Explanation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ask = async (q: string) => {
    const clean = q.trim();
    if (!clean || busy) return;
    setBusy(true);
    setError(null);
    try {
      setAnswer(await client.explain(clean));
    } catch {
      setError("Couldn't reach your agents right now. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    ask(question);
  };

  return (
    <Card>
      <SectionHeading
        eyebrow="Trust through transparency"
        title="Ask why"
        hint="Every agent move comes with its reasoning, grounded in your real data."
      />

      <div className="flex flex-wrap gap-2">
        <GhostButton onClick={() => ask(PRESET_QUESTION)}>{PRESET_QUESTION}</GhostButton>
      </div>

      <form onSubmit={submit} className="mt-3 flex flex-col gap-3 sm:flex-row">
        <label htmlFor="why-input" className="sr-only">
          Ask your agents anything
        </label>
        <input
          id="why-input"
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Or ask anything, in your own words…"
          disabled={busy}
          className="w-full flex-1 rounded-xl border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/60 transition-colors duration-200 focus:border-accent disabled:opacity-60"
        />
        <PrimaryButton type="submit" disabled={busy || !question.trim()}>
          Ask
        </PrimaryButton>
      </form>

      <div className="mt-5" aria-live="polite">
        {busy && (
          <div className="py-4">
            <TypingDots label="Your agents are explaining" />
          </div>
        )}
        {error && (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        )}
        {answer && !busy && (
          <div className="rounded-xl bg-muted/60 p-5">
            <p className="text-sm leading-relaxed text-foreground">{answer.answer}</p>
            <ul className="mt-4 space-y-2 border-t border-border pt-4">
              {answer.facts.map((fact) => (
                <li key={fact.label} className="text-sm">
                  <span className="font-semibold text-accent">{fact.label}: </span>
                  <span className="text-muted-foreground">{fact.detail}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}
