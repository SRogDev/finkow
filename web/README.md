# Finkow — Web Frontend (v2)

Next.js (App Router) frontend for **Finkow**, the source-available AI
investing product. English UI, calm dark "sentient UI", gold (`#F59E0B`)
brand accent, Inter type.

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
    page.tsx                 # the one conversational home
    layout.tsx               # header, footer, metadata
    globals.css              # design tokens + sentient-UI motion
  components/
    GoalInput.tsx            # natural-language goal hero
    PlanCard.tsx             # plain-language plan + allocation bars
    AgentFeed.tsx            # live agent activity with typing indicators
    PortfolioPulse.tsx       # alive portfolio status, plain language
    OpportunityCard.tsx      # opportunity + one-tap paper invest
    Explainer.tsx            # "ask why" grounded explanations
    ui.tsx                   # shared primitives (cards, buttons, disclosures)
  lib/
    finkow-client.ts         # typed v2 API client (mock default, HTTP ready)
    finkow-client.test.ts    # client contract tests
```
