"use client";

import { Map as MapIcon, MessagesSquare, Navigation, Radar } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { AgentEvent, AgentName } from "@/lib/finkow-client";
import { TracingBeam } from "./effects";
import { Card, LiveDot, SectionHeading, TypingDots } from "./ui";

const AGENT_META: Record<AgentName, { icon: typeof Radar; tint: string }> = {
  Radar: { icon: Radar, tint: "text-accent" },
  Pilot: { icon: Navigation, tint: "text-success" },
  Planner: { icon: MapIcon, tint: "text-accent" },
  Explainer: { icon: MessagesSquare, tint: "text-muted-foreground" },
};

const STEP_MS = 1000;
const TYPING_MS = 650;

/**
 * Live agent activity feed. On first load the agents "arrive" one by one
 * with a typing indicator, so the product feels alive. Later events
 * (e.g. after an invest) appear instantly at the top.
 */
export function AgentFeed({ events }: { events: AgentEvent[] }) {
  const [revealed, setRevealed] = useState(0);
  const [typingFor, setTypingFor] = useState<AgentName | null>(null);
  const [introDone, setIntroDone] = useState(false);
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current || events.length === 0) return;
    startedRef.current = true;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setRevealed(events.length);
      setIntroDone(true);
      return;
    }
    const timers: ReturnType<typeof setTimeout>[] = [];
    const count = events.length;
    events.forEach((event, i) => {
      timers.push(
        setTimeout(() => setTypingFor(event.agent), i * STEP_MS),
        setTimeout(
          () => {
            setTypingFor(null);
            setRevealed(i + 1);
            if (i === count - 1) setIntroDone(true);
          },
          i * STEP_MS + TYPING_MS,
        ),
      );
    });
    return () => timers.forEach(clearTimeout);
  }, [events]);

  const shown = introDone ? events : events.slice(0, revealed);

  return (
    <Card>
      <SectionHeading
        eyebrow="Agents at work"
        title="Live activity"
        hint="Your agents never sleep. Every move arrives with its reasoning."
      />
      <div className="mb-4 flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <LiveDot />
        <span aria-live="polite">{typingFor ? `${typingFor} is working…` : "All caught up"}</span>
        {typingFor && <TypingDots label={`${typingFor} is working`} />}
      </div>

      <TracingBeam>
        <ol className="space-y-1 pl-9" aria-live="polite">
          {shown.map((event, i) => {
            const meta = AGENT_META[event.agent];
            const Icon = meta.icon;
            return (
              <li
                key={event.id}
                className={`feed-item flex items-start gap-3 rounded-xl px-3 py-2.5 ${
                  i === 0 ? "bg-muted/50" : ""
                }`}
              >
                <span
                  className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted ${meta.tint}`}
                >
                  <Icon className="h-4 w-4" aria-hidden />
                </span>
                <div className="min-w-0">
                  <p className="text-sm leading-relaxed text-foreground">{event.text}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {event.agent} · {event.at}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      </TracingBeam>
    </Card>
  );
}
