# Finkow — Visual Direction

> Practical visual brief for builders, from SPEC §4 (S15). 2026-10-16.
> Authority: `design-system/finkow/MASTER.md` is the single visual source of
> truth; this document is the *why* and *how far* behind the tokens.

## Idea

Finkow is a **minimalist financial observatory** — a calm room you step into
to understand your money, not a cockpit you fly all day. Quiet surfaces,
one confident voice, gold where it matters.

## Palette

- **Background:** dark charcoal (`#0A0A0B`). Near-black, warm, never cold blue-black.
- **Gold:** `#F59E0B`, used **selectively**: important actions, AI activity,
  key values, discoveries, headings, justified outcomes. Gold is a signal,
  not decoration — if everything is gold, nothing is.
- **Semantics:** green = positive financial movement, red = negative
  financial movement. Never green or red for brand or primary actions.
- **Balance:** roughly 60/30/10 — 60% dark surface, 30% secondary surface/text,
  10% gold accents.
- **Forbidden:** green-as-primary-action, purple/blue "AI glow" palettes,
  multi-color chart confetti, rainbow data-viz.

## Typography

- **Functional:** Inter — UI, numbers, labels, dense information.
- **Editorial:** Fraunces — headings, hero moments, the "voice" of Finkow.
  Used sparingly so it stays distinctive.
- Numbers are tabular where they align (portfolio values, ledgers).

## Layout principles

- Home is a **conversational workspace**, not a trading dashboard: persistent
  portfolio indicator, natural-language input, recent activity, discoveries —
  a few entry points, not a chart grid.
- No conventional trading-dashboard patterns: no candlestick walls, no
  ticker-tape headers, no crowded multi-chart home.
- Information hierarchy, portfolio view: total value → period performance →
  gains/losses → allocation → positions → recent transactions → full history.
- Mobile-first: 375px is a first-class citizen, not a degraded view.
- Data honesty in the visual layer: source and freshness of key values shown;
  virtual capital labeled; deposits never styled as gains; no fake activity,
  no artificial liveliness.

## Anti-AI-slop rules

- No generic unadapted component-library look; no default shadcn-everywhere.
- No excessive gradients, glassmorphism, glows, or drop-shadows as the
  aesthetic.
- No chart-crowded screens; one chart earns its place by answering a question.
- No purple-blue "AI sparkle" clichés, no emoji as icons (SVG only:
  Heroicons/Lucide).
- Gold gradients allowed for hero moments only (e.g. `#FFE9A8 → #F59E0B →
  #B45309`); never as a general background wash.
- Every element must justify itself to the user's task; decoration is a bug.

## Motion

- **Purposeful motion:** functional (state changes, transitions), informative
  (drawing attention to something that changed), expressive (rare, celebratory
  moments). Purposeless animation is forbidden.
- **Calm when idle:** the app at rest is still. No ambient pulsing, no
  looping decorative motion.
- `prefers-reduced-motion` is respected everywhere: decorative motion off,
  transitions minimal, media paused or rendered static.
- Smooth state transitions (150–300ms); no layout-shifting hovers; no
  content hidden behind fixed navbars; no horizontal scroll on mobile.

## Accessibility & responsiveness (kept from the old system)

- Minimum 4.5:1 text contrast (light and dark surfaces).
- Visible focus states for keyboard navigation; all interactive elements
  keyboard-operable.
- Verified at 375px, 768px, 1024px, 1440px viewports.
- Moving media must be pausable; pause offscreen/hidden media automatically.
