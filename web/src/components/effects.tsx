"use client";

import { Children, type ReactNode, useRef } from "react";

/* ------------------------------------------------------------------ */
/* v2.1 Aceternity-style elements — implemented in-repo, Tailwind +    */
/* CSS only. Decorative layers are aria-hidden; content stays clean.   */
/* ------------------------------------------------------------------ */

/** Lamp glow blooming from the top of the hero — static warmth, no ambient
 * motion (the interface stays calm when idle). */
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
 * Calm snap rail for discoveries. No auto-motion: the interface stays
 * still when idle (VISUAL_DIRECTION.md) and the user scrolls or swipes
 * at their own pace. Keyboard users tab through real cards.
 */
export function ScrollRail({
  children,
  label,
  className = "",
}: {
  children: ReactNode;
  label: string;
  className?: string;
}) {
  return (
    <section className={`scroll-rail ${className}`} aria-label={label}>
      <div className="flex gap-4">
        {Children.map(children, (child, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: the rail is a static ordered sequence.
          <div key={i} className="scroll-rail-item">
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
