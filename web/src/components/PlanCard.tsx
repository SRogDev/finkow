"use client";

import type { Plan } from "@/lib/finkow-client";
import { Card, Reveal, SectionHeading, WhyDetails } from "./ui";

export function PlanCard({ plan }: { plan: Plan }) {
  return (
    <Reveal className="reveal-visible">
      <Card aria-live="polite">
        <SectionHeading
          eyebrow="Your plan"
          title={plan.headline}
          hint={`${plan.horizon} · ${riskLabel(plan.risk)}`}
        />
        <p className="max-w-2xl text-base leading-relaxed text-foreground/90">{plan.summary}</p>

        <div className="mt-6 space-y-4">
          {plan.allocations.map((slice, i) => (
            <div key={slice.label}>
              <div className="mb-1.5 flex items-baseline justify-between gap-4">
                <span className="text-sm font-medium text-foreground">{slice.label}</span>
                <span className="tnum text-sm font-semibold text-accent">{slice.percent}%</span>
              </div>
              <div
                className="h-2 overflow-hidden rounded-full bg-muted"
                role="img"
                aria-label={`${slice.label}: ${slice.percent} percent`}
              >
                <div
                  className="h-full rounded-full bg-accent transition-[width] duration-700 ease-out"
                  style={{ width: `${slice.percent}%`, transitionDelay: `${i * 90}ms` }}
                />
              </div>
              <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{slice.why}</p>
            </div>
          ))}
        </div>

        <div className="mt-6 rounded-xl bg-muted/60 px-4 py-3 text-sm leading-relaxed text-muted-foreground">
          {plan.monthlyNote}
        </div>

        <WhyDetails
          points={[
            "Built for your words, not a template: low risk means the calm slices get the biggest share.",
            "Every slice earns its place — if a trend fades, your agents tell you before they move anything.",
            "This is paper money while you learn. Real-money investing arrives later, with brokerage connections.",
          ]}
        />
      </Card>
    </Reveal>
  );
}

function riskLabel(risk: Plan["risk"]): string {
  return risk === "low" ? "Low risk" : risk === "medium" ? "Medium risk" : "Higher risk";
}
