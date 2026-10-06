import { Check, ChevronDown, Info } from "lucide-react";
import type { ReactNode } from "react";

/* ------------------------------------------------------------------ */
/* Layout primitives                                                   */
/* ------------------------------------------------------------------ */

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl border border-border bg-card p-6 ${className}`}>
      {children}
    </section>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  hint,
}: {
  eyebrow: string;
  title: string;
  hint?: string;
}) {
  return (
    <div className="mb-5">
      <p className="mb-1 text-xs font-semibold uppercase tracking-[0.14em] text-accent">
        {eyebrow}
      </p>
      <h2 className="text-2xl font-semibold tracking-tight text-foreground">{title}</h2>
      {hint && (
        <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-muted-foreground">{hint}</p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Buttons                                                             */
/* ------------------------------------------------------------------ */

/**
 * Gold gradient CTA with a sheen sweep on hover — the "gold mine"
 * primary action. Wealth and solidity, never flashy.
 */
export function GoldButton({
  children,
  onClick,
  disabled = false,
  type = "button",
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`btn-sheen inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl gold-bg px-5 py-2.5 text-sm font-semibold text-on-accent shadow-[0_8px_30px_-8px_rgba(245,158,11,0.45)] transition-all duration-200 hover:brightness-110 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none disabled:hover:brightness-100 ${className}`}
    >
      {children}
    </button>
  );
}

export function PrimaryButton({
  children,
  onClick,
  disabled = false,
  type = "button",
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl bg-accent px-5 py-2.5 text-sm font-semibold text-on-accent transition-all duration-200 hover:brightness-110 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:brightness-100 ${className}`}
    >
      {children}
    </button>
  );
}

export function GhostButton({
  children,
  onClick,
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors duration-200 hover:border-accent/60 hover:text-accent ${className}`}
    >
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Sentient-UI atoms: typing indicator, live dot, reveal, disclosure    */
/* ------------------------------------------------------------------ */

/** Three-dot "agent is thinking" indicator. */
export function TypingDots({ label = "Thinking" }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5" role="status" aria-label={label}>
      <span className="typing-dot" aria-hidden />
      <span className="typing-dot typing-dot-2" aria-hidden />
      <span className="typing-dot typing-dot-3" aria-hidden />
      <span className="sr-only">{label}…</span>
    </span>
  );
}

/** Breathing dot that marks something as alive right now. */
export function LiveDot({ className = "" }: { className?: string }) {
  return <span className={`live-dot ${className}`} aria-hidden />;
}

/**
 * Fades/slides children in when they enter the viewport.
 * Content is visible by default; the animation only enhances.
 */
export function Reveal({
  children,
  className = "",
  delayMs = 0,
}: {
  children: ReactNode;
  className?: string;
  delayMs?: number;
}) {
  return (
    <div className={`reveal ${className}`} style={{ transitionDelay: `${delayMs}ms` }}>
      {children}
    </div>
  );
}

/** Plain-language "why" disclosure used on every agent-driven card. */
export function WhyDetails({ points, riskNote }: { points: string[]; riskNote?: string }) {
  return (
    <details className="why-details group mt-4">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 text-sm font-medium text-accent transition-colors duration-200 hover:brightness-110 [&::-webkit-details-marker]:hidden">
        <ChevronDown
          className="h-4 w-4 transition-transform duration-200 group-open:rotate-180"
          aria-hidden
        />
        Why your agents like this
      </summary>
      <ul className="mt-3 space-y-2">
        {points.map((point) => (
          <li
            key={point}
            className="flex items-start gap-2 text-sm leading-relaxed text-foreground/90"
          >
            <Check className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden />
            <span>{point}</span>
          </li>
        ))}
      </ul>
      {riskNote && (
        <p className="mt-3 flex items-start gap-2 rounded-lg bg-muted/60 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          <span>{riskNote}</span>
        </p>
      )}
    </details>
  );
}

/* ------------------------------------------------------------------ */
/* Display formatting (display-only; the client owns all money values)  */
/* ------------------------------------------------------------------ */

export function formatUsd(n: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n);
}

export function formatSignedUsd(n: number): string {
  const sign = n > 0 ? "+" : n < 0 ? "−" : "";
  return `${sign}${formatUsd(Math.abs(n))}`;
}
