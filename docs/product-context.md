# Finkow — Product Context

> Extracted from Roger's product conversations (2026-09-26). Canonical spec for builders.

## Identity

**Finkow** is an open-source AI-native financial learning and investing sandbox.
Core idea: **"Learn finance by interacting with a realistic financial world."**

It is NOT a budgeting / expense-tracking / household-finance app. It is a
**financial simulator + AI financial interface + learning environment**.

Focus: investing, wealth creation, financial markets, instruments, opportunities,
decision-making, understanding consequences, eventually AI-operated financial actions.

## Philosophy

Reversed learning funnel:

Explore → Ask → Simulate → Act → Observe → Understand → Learn → Explore again

The user learns because they interact with a functioning financial environment.

## Main experience

- User starts with **fake money** (virtual sandbox account).
- Inspect assets, ask questions, ask AI about opportunities.
- Simulate investments, buy/sell with virtual money, construct portfolios.
- Observe price changes, gains/losses, decision consequences over time.
- Ask "why did this happen?" — AI explains in context of their actual actions.
- Goal: build **financial intuition through interaction**, not "win" the simulation.

## Sandbox

- **Real market data** where practical; user's money stays 100% virtual.
- Instruments: stocks, bonds, ETFs, crypto (start manageable, expand later).
- Realistic prices, price changes, historical data, portfolio values, transactions, returns.
- Real market movement → user's simulated position → portfolio changes → AI explains.

## AI financial interface

AI is the **primary conversational interface** to financial actions, not a chatbot bolted on:

- What opportunities exist? / What happened to my portfolio? / Why did this asset move?
- What if I invest X? / Compare instruments / Explain this concept.
- Show me a market crash / What risks am I taking? / Simulate this strategy / Execute this action.

## AI opportunity detection (long-term)

Market → AI analysis → potential opportunity → explanation → risks →
simulation → user decision → action. **User stays in control** — detecting ≠ executing.

## AI actions (future)

User: "Invest $500 in this strategy." → AI understands, validates, explains risk,
executes via integration, reports result. **Not in MVP.**

## Real-money mode (future, not MVP)

Learn with fake money → confidence → connect real account → AI assists/executes.
Requires security, authorization, compliance, risk controls, auditing. Explicitly post-MVP.

## Educational layer

Contextual, not curricular. User buys ETF → market changes → AI explains
diversification → user asks why → experiments again. Concepts arrive inside activity.

## Scenarios (future)

AI-generated/facilitated: market crash, inflation, sector boom, rate changes,
crypto volatility, company collapse, recession, news shocks, concentration tests.

## Portfolio

Cash, positions, allocation, returns, gains/losses, risk, diversification,
transaction + portfolio history, performance over time. Analytics expand gradually.

## Monetization (future)

Open source. Possible hosted model: tiny transaction fee per financial action;
possible financial-product placements. **Post-MVP. No ads in core product.**

## MVP loop

Create user → virtual money → explore market → inspect assets → ask AI →
simulate → buy/sell virtually → observe real market movement → portfolio changes →
ask AI what happened → learn → repeat.

MVP proves: **"Can a person develop financial intuition by interacting with a
realistic financial sandbox through AI?"**

## Architecture

```
Next.js
  ↓
FastAPI
  ├── User / Sandbox / Market Data
  ├── Portfolio / Positions / Transactions
  └── Financial Domain Logic
        ↓
     AI Layer (structured ops — AI calls financial operations,
               never mutates DB state directly)
        ↓
  Opportunity / Learning / Simulation / Actions
        ↓
  Future: real financial APIs
```

## Non-negotiables

1. About wealth/investing, not budgeting. 2. Learning through doing.
3. Virtual money first. 4. Real market data. 5. AI = conversational interface.
6. AI identifies + explains opportunities. 7. Real money = future phase.
8. Monetization secondary. 9. Stay genuinely usable — ruthless MVP scope.
