# finkow — Project Brief

> Full project context in one file. Hand this to ANOTHER AI (GPT, etc.) for planning
> and ideation, then bring the refined specs back. Keep this file accurate — it is the handoff doc.
> For the current timeline see `STATUS.md`. For how to work in this repo see `AGENTS.md`.

## One-liner
Finkow is Roger's AI-native financial learning sandbox: virtual money + real market data, with AI as the primary interface.

## Problem & audience
Finance apps assume literacy; learning with real money is scary and paper trading is boring. Nobody built the AI-native sandbox where you learn by doing with virtual money and real data.

## Product (what it is / is not)
AI-native financial learning sandbox: virtual money, real market data (Yahoo Finance chart API as keyless fallback; stooq.com is blocked in this sandbox), AI as the primary interface. NOT a trading bot and NOT real-money investing.

## Key decisions (locked)
- Public repo, MIT. Brand gold #F59E0B. Renamed finknow → finkow per Roger.
- Stack: Next.js web + FastAPI api (uv only) + Supabase.
- AI as primary interface — the UI serves the conversation, not the other way around.

## Stack
Next.js web, FastAPI api (uv), Supabase, Yahoo Finance chart API (keyless market data).

## Business model
Not locked — learning sandbox first.

## Open questions
- MVP scaffold completion status (builders in progress).
- Which financial concepts the AI teaches first.
