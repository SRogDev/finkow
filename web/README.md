# Finkow — Web Frontend (v2.1)

Next.js (App Router) frontend for **Finkow**, the source-available AI
investing product. English UI, deep-charcoal "gold mine" design system,
Inter + Fraunces type.

## Design — gold system (v2.1)

Premium "gold mine" feel: wealth, solidity, calm — never flashy casino.

- **Palette**: near-black `#0A0A0B` backgrounds, primary gold `#F59E0B`,
  rich gradients `#FFE9A8 → #F59E0B → #B45309` for hero moments, CTAs,
  and the portfolio pulse.
- **Aceternity-style elements, implemented in-repo** (`components/effects.tsx`,
  Tailwind + CSS, no extra deps): `LampGlow` on the goal screen,
  `SpotlightCard` (cursor-tracking gold light) on opportunities,
  `TracingBeam` on the agent feed, `InfiniteRail` (pauses on hover/focus)
  for the opportunity rail.
- **Sentient + bespoke**: proactive, conversational, ambient, explanatory,
  calm. Every animation resolves to a static state under
  `prefers-reduced-motion`.
- Tokens and keyframes live in `app/globals.css` (`@theme`).

## What it is

One conversational home — not a trading dashboard:

- **Goal input** — "Grow $1,000 over 5 years, low risk" → a plain-language plan.
- **Live agent activity feed** — Radar, Pilot, Planner, Explainer narrate what they do.
- **Portfolio pulse** — your money as a living status, not a spreadsheet.
- **Opportunity cards** — one-tap paper investing, reasoning attached to every card.
- **Ask why** — grounded explanations citing the facts behind every move.

Zero finance jargon by default. The user never sees a ticker or a brokerage
screen. All money is paper money.

## API client

`src/lib/finkow-client.ts` is the only way the UI talks to data. It maps 1:1
to the v2 contract (`POST /goals`, `GET /goals/{id}/plan`,
`GET /radar/opportunities`, `POST /portfolio/invest`, `GET /portfolio`,
`POST /explain`, `GET /agents/activity`).

- **Mock adapter (default)** — deterministic demo data, in-memory paper
  portfolio. The UI is fully demonstrable with no backend.
- **HTTP adapter** — set `NEXT_PUBLIC_FINKOW_ADAPTER=http` and
  `NEXT_PUBLIC_FINKOW_API_URL=http://localhost:8000` to talk to the real
  FastAPI backend when it lands.

## Auth (Supabase)

Optional. The app builds and runs **without** Supabase configured — auth is
then gracefully disabled and everyone sees the app (the pre-auth behavior).

To enable sign-in, create a Supabase project and set:

```bash
NEXT_PUBLIC_SUPABASE_URL=https://xyzcompany.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOi...
```

What you get: `@supabase/ssr` session handling (`lib/supabase/`), a root
`proxy.ts` (Next.js 16 convention) that refreshes the session and redirects
anonymous visitors to `/login`, a gold-styled sign-in gate (`/login` —
email+password and magic link), `/auth/callback` + `/auth/confirm` +
`/auth/signout` routes, and a sign-in/sign-out slot in the header.

## Run it

```bash
npm install
npm run dev        # http://localhost:3000
```

## Quality gates

```bash
npm test           # unit tests (node:test, zero deps)
npm run lint       # Biome check — must be clean
npx tsc --noEmit   # strict typecheck — must be clean
npm run build      # Next.js production build — must pass with zero errors
```

## Layout

```
src/
  app/
    page.tsx                 # the one conversational home (server gate → HomeApp)
    login/                   # sign-in gate: page.tsx, LoginForm.tsx, actions.ts
    auth/                    # callback/, confirm/, signout/ route handlers
    layout.tsx               # header (with HeaderAuth slot), footer, metadata
    proxy.ts                 # root proxy: Supabase session refresh (Next 16)
    globals.css              # design tokens + sentient-UI motion
  components/
    HomeApp.tsx              # the client conversational home
    HeaderAuth.tsx           # async server component: sign-in link / sign-out form
    GoalInput.tsx            # natural-language goal hero
    PlanCard.tsx             # plain-language plan + allocation bars
    AgentFeed.tsx            # live agent activity with typing indicators
    PortfolioPulse.tsx       # alive portfolio status, plain language
    OpportunityCard.tsx      # opportunity + one-tap paper invest (spotlight card)
    Explainer.tsx            # "ask why" grounded explanations
    effects.tsx              # LampGlow, SpotlightCard, TracingBeam, InfiniteRail, GoldRule
    ui.tsx                   # shared primitives (cards, buttons incl. GoldButton, disclosures)
  lib/
    finkow-client.ts         # typed v2 API client (mock default, HTTP ready)
    finkow-client.test.ts    # client contract tests
    rail.ts                  # duplicateForLoop helper for the infinite rail
    rail.test.ts             # rail loop tests
    supabase/                # env.ts, client.ts, server.ts, proxy.ts (+ env tests)
    auth/                    # validation.ts (+ tests) — auth input validation
```
