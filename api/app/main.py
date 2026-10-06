"""Finkow FastAPI backend — v2: AI investing agents on virtual money.

v1 endpoints (accounts, orders, quotes, portfolio, transactions, history,
/ai/explain) are unchanged. v2 adds provider ports (MarketData/LLM/WebSearch
with AIsa + mock + free direct adapters), the agent pipeline (GoalPlanner,
OpportunityRadar, PortfolioPilot, Explainer) with an append-only event log,
and the goal/radar/invest/explain/activity endpoints.

Paper money only — there is no real-money code path in this service.
"""

from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import ai as ai_ops
from app.agents.events import EventLog
from app.agents.explainer import Explainer
from app.agents.pilot import PortfolioPilot
from app.agents.planner import Allocation, GoalPlanner, parse_goal
from app.agents.radar import OpportunityRadar
from app.market import (
    CachedMarketData,
    MarketDataError,
    MarketDataUnavailable,
    Quote,
    SymbolNotFound,
)
from app.money import cash_str, qty_str, to_cash, to_qty
from app.portfolio import PortfolioView, value_portfolio
from app.ports import LLMPort, MarketDataPort, ProviderError, WebSearchPort
from app.providers import build_llm, build_market_port, build_search
from app.store import InMemoryStore, Snapshot, utcnow
from app.trading import (
    InsufficientFundsError,
    InsufficientPositionError,
    execute_paper_buy,
    execute_paper_sell,
)

app = FastAPI(title="Finkow API", version="0.2.0")


def _cors_origins() -> list[str]:
    """Allowed browser origins.

    Override with ``FINKOW_CORS_ORIGINS`` (comma-separated, e.g.
    ``https://finkow.example.com``). Defaults cover local Next.js dev.
    """
    raw = os.environ.get("FINKOW_CORS_ORIGINS", "")
    if raw.strip():
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


# The Next.js frontend calls the API directly from the browser
# (fetch to NEXT_PUBLIC_API_URL), so the backend must serve CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["content-type"],
    max_age=600,
)

DEFAULT_WATCHLIST = ["AAPL", "MSFT", "NVDA", "VTI", "BND", "BTC", "ETH", "SOL"]

_store = InMemoryStore()
_market: CachedMarketData | None = None
_market_port: MarketDataPort | None = None
_llm: LLMPort | None = None
_search: WebSearchPort | None = None
_events = EventLog()


def get_store() -> InMemoryStore:
    return _store


def get_market() -> CachedMarketData:
    global _market
    if _market is None:
        _market = CachedMarketData()
    return _market


def get_market_port() -> MarketDataPort:
    global _market_port
    if _market_port is None:
        _market_port = build_market_port()
    return _market_port


def get_llm() -> LLMPort:
    global _llm
    if _llm is None:
        _llm = build_llm()
    return _llm


def get_search() -> WebSearchPort:
    global _search
    if _search is None:
        _search = build_search()
    return _search


def get_events() -> EventLog:
    return _events


def reset_state() -> None:
    """Test hook: fresh store, market, ports, and event log between tests."""
    global _store, _market, _market_port, _llm, _search, _events
    _store = InMemoryStore()
    _market = None
    _market_port = None
    _llm = None
    _search = None
    _events = EventLog()


# ---------------------------------------------------------------- requests


class CreateAccountRequest(BaseModel):
    email: str | None = None


class OrderRequest(BaseModel):
    account_id: str
    symbol: str
    side: str  # "buy" | "sell"
    quantity: str  # decimal string, e.g. "10" or "0.5"


class ExplainRequest(BaseModel):
    account_id: str
    question: str


class CreateGoalRequest(BaseModel):
    text: str
    amount: str | None = None  # decimal string; overrides the amount parsed from text


class AllocationInput(BaseModel):
    symbol: str
    weight: str  # decimal string, 0 < w <= 1


class InvestRequest(BaseModel):
    account_id: str
    allocations: list[AllocationInput]


# ---------------------------------------------------------------- helpers


@app.get("/api/quotes/{symbol}")
async def get_quote(symbol: str, market: CachedMarketData = Depends(get_market)) -> dict:
    try:
        quote = await market.get_quote(symbol)
    except SymbolNotFound as exc:
        raise HTTPException(status_code=404, detail=f"unknown symbol: {symbol}") from exc
    except MarketDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"market data unavailable: {exc}") from exc
    return {
        "symbol": quote.symbol,
        "price": qty_str(quote.price),
        "currency": quote.currency,
        "as_of": quote.as_of.isoformat(),
        "provider": quote.provider,
        "stale": quote.stale,
    }


async def _portfolio_view_from(account_id: str, store: InMemoryStore, fetch) -> PortfolioView:
    """Value a portfolio; ``fetch(symbol)`` returns a Quote or None (stale)."""
    account = store.get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    positions = store.get_positions(account_id)
    quotes: dict[str, Quote] = {}
    for pos in positions:
        quote = await fetch(pos.symbol)
        if quote is not None:
            quotes[pos.symbol] = quote
    return value_portfolio(account, positions, quotes)


async def _portfolio_view(account_id: str, store: InMemoryStore, market: CachedMarketData):
    async def fetch(symbol: str):
        try:
            return await market.get_quote(symbol)
        except MarketDataUnavailable:
            return None  # value_portfolio falls back to avg_cost, marked stale

    return await _portfolio_view_from(account_id, store, fetch)


async def _portfolio_view_port(account_id: str, store: InMemoryStore, market: MarketDataPort):
    async def fetch(symbol: str):
        try:
            return await market.get_quote(symbol)
        except (MarketDataError, ProviderError):
            return None

    return await _portfolio_view_from(account_id, store, fetch)


def _serialize_portfolio(pv: PortfolioView) -> dict:
    return {
        "account_id": pv.account_id,
        "cash": cash_str(pv.cash),
        "initial_cash": cash_str(pv.initial_cash),
        "total_value": cash_str(pv.total_value),
        "total_return": cash_str(pv.total_return),
        "total_return_pct": format(pv.total_return_pct, ".2f"),
        "allocation": {k: format(v, ".4f") for k, v in pv.allocation.items()},
        "as_of": pv.as_of.isoformat(),
        "positions": [
            {
                "symbol": p.symbol,
                "quantity": qty_str(p.qty),
                "avg_cost": cash_str(p.avg_cost),
                "price": qty_str(p.price),
                "market_value": cash_str(p.market_value),
                "unrealized_pnl": cash_str(p.unrealized_pnl),
                "unrealized_pnl_pct": format(p.unrealized_pnl_pct, ".2f"),
                "stale": p.stale,
            }
            for p in pv.positions
        ],
    }


def _serialize_plan(goal_id: str, plan: dict) -> dict:
    return {
        "goal_id": goal_id,
        "summary_plain": plan["summary_plain"],
        "horizon_years": plan["horizon_years"],
        "risk_level": plan["risk_level"],
        "allocations": [
            {
                "symbol": a["symbol"],
                "weight": format(Decimal(str(a["weight"])), ".4f"),
                "rationale": a.get("rationale", ""),
            }
            for a in plan["allocations"]
        ],
    }


# ---------------------------------------------------------------- v1 routes (unchanged)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": "0.2.0"}


@app.post("/api/accounts")
def create_account(body: CreateAccountRequest, store: InMemoryStore = Depends(get_store)) -> dict:
    account = store.create_account(email=body.email)
    return {
        "account_id": account.id,
        "cash": cash_str(account.cash),
        "initial_cash": cash_str(account.initial_cash),
        "created_at": account.created_at.isoformat(),
    }


@app.post("/api/orders")
async def place_order(
    body: OrderRequest,
    store: InMemoryStore = Depends(get_store),
    market: CachedMarketData = Depends(get_market),
) -> dict:
    side = body.side.lower()
    if side not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="side must be 'buy' or 'sell'")
    try:
        qty = to_qty(Decimal(body.quantity))
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=400, detail="quantity must be a decimal number") from exc
    if qty <= 0:
        raise HTTPException(status_code=400, detail="quantity must be positive")

    account = store.get_account(body.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")

    try:
        quote = await market.get_quote(body.symbol)
    except SymbolNotFound as exc:
        raise HTTPException(status_code=404, detail=f"unknown symbol: {body.symbol}") from exc
    except MarketDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"market data unavailable: {exc}") from exc
    symbol, price = quote.symbol, quote.price

    # Paper-trade execution shares one code path with the PortfolioPilot agent.
    try:
        if side == "buy":
            txn = execute_paper_buy(store, account.id, symbol, qty, price)
        else:
            txn = execute_paper_sell(store, account.id, symbol, qty, price)
    except InsufficientFundsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InsufficientPositionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    pv = await _portfolio_view(account.id, store, market)
    store.add_snapshot(
        Snapshot(
            account_id=account.id,
            total_value=pv.total_value,
            cash=account.cash,
            created_at=utcnow(),
        )
    )
    return {
        "transaction_id": txn.id,
        "side": side,
        "symbol": symbol,
        "quantity": qty_str(qty),
        "price": qty_str(price),
        "cash_after": cash_str(account.cash),
        "realized_pnl": cash_str(txn.realized_pnl) if txn.realized_pnl is not None else None,
        "stale_price": quote.stale,
    }


@app.get("/api/accounts/{account_id}/portfolio")
async def get_portfolio(
    account_id: str,
    store: InMemoryStore = Depends(get_store),
    market: CachedMarketData = Depends(get_market),
) -> dict:
    return _serialize_portfolio(await _portfolio_view(account_id, store, market))


@app.get("/api/accounts/{account_id}/transactions")
def get_transactions(account_id: str, store: InMemoryStore = Depends(get_store)) -> dict:
    if store.get_account(account_id) is None:
        raise HTTPException(status_code=404, detail="account not found")
    return {
        "transactions": [
            {
                "id": t.id,
                "symbol": t.symbol,
                "side": t.side,
                "quantity": qty_str(t.qty),
                "price": qty_str(t.price),
                "cash_delta": cash_str(t.cash_delta),
                "realized_pnl": cash_str(t.realized_pnl) if t.realized_pnl is not None else None,
                "created_at": t.created_at.isoformat(),
            }
            for t in store.list_transactions(account_id)
        ]
    }


@app.get("/api/accounts/{account_id}/history")
def get_history(account_id: str, store: InMemoryStore = Depends(get_store)) -> dict:
    if store.get_account(account_id) is None:
        raise HTTPException(status_code=404, detail="account not found")
    return {
        "snapshots": [
            {
                "total_value": cash_str(s.total_value),
                "cash": cash_str(s.cash),
                "created_at": s.created_at.isoformat(),
            }
            for s in store.list_snapshots(account_id)
        ]
    }


@app.post("/api/ai/explain")
async def ai_explain(
    body: ExplainRequest,
    store: InMemoryStore = Depends(get_store),
    market: CachedMarketData = Depends(get_market),
) -> dict:
    pv = await _portfolio_view(body.account_id, store, market)
    return await ai_ops.explain_portfolio(pv, body.question)


# ---------------------------------------------------------------- v2 routes: goals + agents


@app.post("/api/goals")
def create_goal(
    body: CreateGoalRequest,
    store: InMemoryStore = Depends(get_store),
    events: EventLog = Depends(get_events),
) -> dict:
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    if body.amount is not None:
        try:
            amount = to_cash(Decimal(body.amount))
        except (InvalidOperation, ValueError) as exc:
            raise HTTPException(
                status_code=400, detail="amount must be a decimal number"
            ) from exc
        if amount <= 0:
            raise HTTPException(status_code=400, detail="amount must be positive")
    else:
        amount = parse_goal(text).amount
    account = store.create_account(email=None, initial_cash=amount)
    goal = store.create_goal(text=text, amount=amount, account_id=account.id)
    events.append(
        "planner",
        "goal.created",
        {"goal_id": goal.id, "account_id": account.id, "amount": str(amount)},
    )
    return {
        "goal_id": goal.id,
        "account_id": account.id,
        "amount": cash_str(amount),
        "text": text,
        "created_at": goal.created_at.isoformat(),
    }


@app.get("/api/goals/{goal_id}")
def get_goal(goal_id: str, store: InMemoryStore = Depends(get_store)) -> dict:
    goal = store.get_goal(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="goal not found")
    return {
        "goal_id": goal.id,
        "text": goal.text,
        "amount": cash_str(goal.amount),
        "account_id": goal.account_id,
        "created_at": goal.created_at.isoformat(),
    }


@app.get("/api/goals/{goal_id}/plan")
async def get_goal_plan(
    goal_id: str,
    store: InMemoryStore = Depends(get_store),
    llm: LLMPort = Depends(get_llm),
    events: EventLog = Depends(get_events),
) -> dict:
    goal = store.get_goal(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="goal not found")
    cached = store.get_plan(goal_id)
    if cached is not None:
        return _serialize_plan(goal_id, cached)
    planner = GoalPlanner(llm, events)
    try:
        plan = await planner.plan(goal.text)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    plan_dict = {
        "summary_plain": plan.summary_plain,
        "horizon_years": plan.horizon_years,
        "risk_level": plan.risk,
        "allocations": [
            {"symbol": a.symbol, "weight": str(a.weight), "rationale": a.rationale}
            for a in plan.allocations
        ],
    }
    store.save_plan(goal_id, plan_dict)
    return _serialize_plan(goal_id, plan_dict)


@app.get("/api/radar/opportunities")
async def radar_opportunities(
    symbols: str | None = None,
    goal_id: str | None = None,
    store: InMemoryStore = Depends(get_store),
    market: MarketDataPort = Depends(get_market_port),
    llm: LLMPort = Depends(get_llm),
    events: EventLog = Depends(get_events),
) -> dict:
    watch: list[str] = []
    if symbols:
        watch = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    elif goal_id:
        if store.get_goal(goal_id) is None:
            raise HTTPException(status_code=404, detail="goal not found")
        plan = store.get_plan(goal_id)
        if plan:
            watch = [str(a["symbol"]).upper() for a in plan["allocations"]]
    if not watch:
        watch = list(DEFAULT_WATCHLIST)
    radar = OpportunityRadar(market, llm, events)
    try:
        opportunities = await radar.scan(watch)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "opportunities": [
            {
                "symbol": o.symbol,
                "score": o.score,
                "price": str(o.price),
                "reasoning": o.reasoning,
            }
            for o in opportunities
        ],
        "provider": market.name,
    }


@app.post("/api/portfolio/invest")
async def invest_portfolio(
    body: InvestRequest,
    store: InMemoryStore = Depends(get_store),
    market: MarketDataPort = Depends(get_market_port),
    events: EventLog = Depends(get_events),
) -> dict:
    allocations: list[Allocation] = []
    for item in body.allocations:
        try:
            weight = Decimal(item.weight)
        except (InvalidOperation, ValueError) as exc:
            raise HTTPException(
                status_code=400, detail="weight must be a decimal number"
            ) from exc
        if weight <= 0 or weight > 1:
            raise HTTPException(status_code=400, detail="weight must be between 0 and 1")
        symbol = item.symbol.strip().upper()
        if not symbol:
            raise HTTPException(status_code=400, detail="symbol is required")
        allocations.append(Allocation(symbol, weight, ""))
    if not allocations:
        raise HTTPException(status_code=400, detail="at least one allocation is required")
    pilot = PortfolioPilot(store, market, events)
    try:
        result = await pilot.invest(body.account_id, allocations)
    except ValueError as exc:
        if "account not found" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "account_id": result.account_id,
        "trades": [
            {
                "side": t.side,
                "symbol": t.symbol,
                "quantity": t.quantity,
                "price": t.price,
            }
            for t in result.trades
        ],
        "total_invested": cash_str(result.total_invested),
    }


@app.get("/api/goals/{goal_id}/portfolio")
async def get_goal_portfolio(
    goal_id: str,
    store: InMemoryStore = Depends(get_store),
    market: MarketDataPort = Depends(get_market_port),
) -> dict:
    goal = store.get_goal(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="goal not found")
    return _serialize_portfolio(await _portfolio_view_port(goal.account_id, store, market))


@app.post("/api/explain")
async def explain_v2(
    body: ExplainRequest,
    store: InMemoryStore = Depends(get_store),
    market: MarketDataPort = Depends(get_market_port),
    llm: LLMPort = Depends(get_llm),
    search: WebSearchPort = Depends(get_search),
    events: EventLog = Depends(get_events),
) -> dict:
    explainer = Explainer(store, market, llm, search, events)
    try:
        return await explainer.explain(body.account_id, body.question)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/agents/activity")
def agent_activity(
    agent: str | None = None,
    limit: int = 50,
    events: EventLog = Depends(get_events),
) -> dict:
    listed = events.list(agent=agent, limit=max(limit, 1))
    return {
        "events": [
            {
                "id": e.id,
                "agent": e.agent,
                "kind": e.kind,
                "payload": e.payload,
                "created_at": e.created_at.isoformat(),
            }
            for e in listed
        ]
    }
