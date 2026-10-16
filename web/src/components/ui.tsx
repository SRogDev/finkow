import { AlertTriangle, Check, ChevronDown, Clock, Info, RotateCcw } from "lucide-react";
import type { ReactNode } from "react";
import { formatSignedMoney, formatSignedPercent } from "@/lib/format";

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
/* Card title, loading / error states                                   */
/* ------------------------------------------------------------------ */

/** Card heading with an optional right-side action slot (badges, links). */
export function CardTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3">
      <h3 className="font-display text-xl font-semibold tracking-tight text-foreground">
        {children}
      </h3>
      {action}
    </div>
  );
}

/** Calm loading state: gold typing dots + label, never a spinner wall. */
export function LoadingState({ label }: { label: string }) {
  return (
    <div
      className="flex items-center gap-3 rounded-2xl border border-border bg-card px-6 py-10"
      role="status"
      aria-label={label}
    >
      <TypingDots label={label} />
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  );
}

/** Honest error state: what happened, one retry action. */
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      className="flex flex-col items-start gap-3 rounded-2xl border border-destructive/30 bg-card px-6 py-8"
      role="alert"
    >
      <p className="flex items-start gap-2 text-sm leading-relaxed text-foreground">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden />
        <span>{message}</span>
      </p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors duration-200 hover:border-accent/60 hover:text-accent"
        >
          <RotateCcw className="h-4 w-4" aria-hidden />
          Try again
        </button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Form field + shared input class                                     */
/* ------------------------------------------------------------------ */

/** Input class per MASTER.md: 16px text (no iOS zoom), gold focus ring. */
export const inputClassName =
  "w-full rounded-xl border border-border bg-background px-4 py-2.5 text-base text-foreground placeholder:text-muted-foreground/60 transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-[3px] focus:ring-accent/25 disabled:opacity-60";

/** Labeled form field with helper hint. Pass htmlFor + a matching input id. */
export function Field({
  label,
  hint,
  htmlFor,
  children,
}: {
  label: string;
  hint?: string;
  htmlFor?: string;
  children: ReactNode;
}) {
  return (
    <div className="block">
      <label htmlFor={htmlFor} className="mb-1.5 block text-sm font-medium text-foreground">
        {label}
      </label>
      {children}
      {hint && (
        <span className="mt-1.5 block text-xs leading-relaxed text-muted-foreground">{hint}</span>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Financial display: signed values, badges (green/red = movement only)*/
/* ------------------------------------------------------------------ */

/**
 * Signed money in financial semantics: green = positive movement,
 * red = negative, neutral = zero. Accepts API decimal strings or numbers.
 */
export function SignedMoney({ value }: { value: string | number }) {
  const text = typeof value === "number" ? formatSignedUsd(value) : formatSignedMoney(value);
  const n = Number(value);
  const tone =
    !Number.isFinite(n) || n === 0
      ? "text-muted-foreground"
      : n > 0
        ? "text-success"
        : "text-destructive";
  return <span className={`tnum font-medium ${tone}`}>{text}</span>;
}

/** Signed percent with the same financial semantics as SignedMoney. */
export function SignedPercent({ value }: { value: string | number }) {
  const text =
    typeof value === "number"
      ? `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value).toFixed(2)}%`
      : formatSignedPercent(value);
  const n = Number(value);
  const tone =
    !Number.isFinite(n) || n === 0
      ? "text-muted-foreground"
      : n > 0
        ? "text-success"
        : "text-destructive";
  return <span className={`tnum font-medium ${tone}`}>{text}</span>;
}

/** Marks a quote that is older than the freshness window. */
export function StaleBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-accent/30 bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent">
      <Clock className="h-3 w-3" aria-hidden />
      Stale quote
    </span>
  );
}

/**
 * Whether an AI answer is grounded in the user's real portfolio data.
 * Gold = grounded; quiet = model-only answer.
 */
export function GroundedBadge({ grounded }: { grounded: boolean }) {
  if (grounded) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-accent/40 bg-accent/10 px-2.5 py-0.5 text-xs font-medium text-accent">
        <Check className="h-3 w-3" aria-hidden />
        Grounded in your data
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
      <Info className="h-3 w-3" aria-hidden />
      Model answer
    </span>
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
