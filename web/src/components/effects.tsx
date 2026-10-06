"use client";

import { Children, type ReactNode, useRef } from "react";
import { duplicateForLoop } from "@/lib/rail";

/* ------------------------------------------------------------------ */
/* v2.1 Aceternity-style elements — implemented in-repo, Tailwind +    */
/* CSS only. Decorative layers are aria-hidden; content stays clean.   */
/* ------------------------------------------------------------------ */

/** Lamp glow blooming from the top of the hero — the mine warming up. */
export function LampGlow() {
  return (
    <div className="lamp-glow" aria-hidden>
      <div className="lamp-glow-core" />
      <div className="lamp-glow-halo" />
    </div>
  );
}

/**
 * Card with a gold spotlight that follows the cursor.
 * Purely decorative light — keyboard and touch users see the static card.
 */
export function SpotlightCard({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  const onMove = (e: React.MouseEvent) => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    el.style.setProperty("--spot-x", `${e.clientX - rect.left}px`);
    el.style.setProperty("--spot-y", `${e.clientY - rect.top}px`);
  };

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: onMouseMove is a decorative-only spotlight; the card itself has no interactivity and needs no keyboard equivalent.
    <div ref={ref} onMouseMove={onMove} className={`spotlight ${className}`}>
      {children}
    </div>
  );
}

/**
 * Tracing beam for the agent activity feed: a faint gold line with a
 * pulse of light travelling down it. Decorative; the list is untouched.
 */
export function TracingBeam({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`tracing-beam ${className}`}>
      <div className="tracing-beam-line" aria-hidden />
      <div className="tracing-beam-pulse" aria-hidden />
      {children}
    </div>
  );
}

/**
 * Infinite-moving-cards rail. The list is duplicated for a seamless loop;
 * the second copy is aria-hidden so screen readers hear each card once.
 * Pauses on hover and on keyboard focus; becomes a plain scroller under
 * reduced motion (see globals.css).
 */
export function InfiniteRail({
  children,
  label,
  className = "",
}: {
  children: ReactNode;
  label: string;
  className?: string;
}) {
  const items = Children.toArray(children);
  const half = items.length;
  const looped = duplicateForLoop(items);

  return (
    <section className={`marquee ${className}`} aria-label={label}>
      <div className="marquee-track">
        {looped.map((child, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: the loop is a static duplicated sequence by design.
          <div key={i} className="marquee-item" aria-hidden={i >= half || undefined}>
            {child}
          </div>
        ))}
      </div>
    </section>
  );
}

/** Thin gold rule — a bespoke divider ornament. */
export function GoldRule({ className = "" }: { className?: string }) {
  return <div className={`gold-rule ${className}`} aria-hidden />;
}
