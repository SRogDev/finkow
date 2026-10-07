"""Finkow FastAPI backend — v2.1: orchestrated agent harness on virtual money.

v1 endpoints (accounts, orders, quotes, portfolio, transactions, history,
/ai/explain) are unchanged. v2 added provider ports and the agent pipeline.
v2.1 adds the orchestrator harness (single entry, 4 specialists, confidence
routing, checkpoints), governance (verifier, audit log, rate limiter, PII
filter), Stripe product billing (flagged), and the brokerage interface (mock).

Paper money only — there is no real-money code path in this service.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal, InvalidOperation

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import ai as ai_ops
from app.agents.events import EventLog
from app.agents.executor import InvestmentExecutor
from app.agents.explainer import Explainer
from app.agents.learning import LearningAgent
from app.agents.pilot import PortfolioPilot
from app.agents.planner import Allocation, GoalPlanner, parse_goal
from app.agents.radar import OpportunityRadar
from app.billing.credits import CREDIT_PACKS, credits_to_usd, get_ledger
from app.billing.stripe_billing import BillingNotConfigured, StripeBilling
from app.brokerage import BrokeragePort, MockBrokerage, OrderSide
from app.governance.audit import AuditLog
from app.governance.metering import (
    CreditsExhausted,
    account_context,
    reset_account,
    reset_metering,
    set_account,
)
from app.governance.pii_filter import PIIFilter
from app.governance.rate_limiter import RateLimiter, wrap_port
from app.harness.orchestrator import Orchestrator, RunRequest
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

app = FastAPI(title="Finkow API", version="0.2.1")


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


@app.middleware("http")
async def _account_context_middleware(request: Request, call_next):
    """Bind the billed account for metering (one context per request).

    The account id can ride in a path parameter (``account_id`` or a goal
    that resolves to one), a query parameter, or the JSON body. Endpoints
    that resolve the account indirectly (e.g. ``/api/executor/confirm`` via
    its approval) set the context explicitly instead.
    """
    account_id: str | None = None
    if "account_id" in request.path_params:
        account_id = request.path_params["account_id"]
    elif "goal_id" in request.path_params:
        goal = _store.get_goal(request.path_params["goal_id"])
        account_id = goal.account_id if goal is not None else None
    elif "account_id" in request.query_params:
        account_id = request.query_params["account_id"] or None
    elif request.method in ("POST", "PUT", "PATCH"):
        try:
            body = await request.body()
            if body:
                payload = json.loads(body)
                value = payload.get("account_id") if isinstance(payload, dict) else None
                account_id = value if isinstance(value, str) and value else None
        except Exception:
            account_id = None
    token = set_account(account_id)
    try:
        return await call_next(request)
    finally:
        reset_account(token)

DEFAULT_WATCHLIST = ["AAPL", "MSFT", "NVDA", "VTI", "BND", "BTC", "ETH", "SOL"]

_store = InMemoryStore()
_market: CachedMarketData | None = None
_market_port: MarketDataPort | None = None
_llm: LLMPort | None = None
_search: WebSearchPort | None = None
_events = EventLog()
_audit = AuditLog()
_brokerage: BrokeragePort | None = None
_pii = PIIFilter()
# Paid-call budget for AIsa ports (per minute, per port kind). 0 disables.
_aisa_limiter = RateLimiter(
    max_calls=int(os.environ.get("FINKOW_AISA_RATE_LIMIT_PER_MIN", "60") or 60),
    window_seconds=60.0,
)


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
        port = build_market_port()
        _market_port = _guard_paid(port, "aisa.market")
    return _market_port


def _guard_paid(port, key: str):
    """Rate-limit paid (AIsa) ports only — mocks and free fallbacks stay open."""
    if os.environ.get("AISA_API_KEY"):
        return wrap_port(port, _aisa_limiter, key)
    return port


def get_llm() -> LLMPort:
    global _llm
    if _llm is None:
        _llm = _guard_paid(build_llm(), "aisa.llm")
    return _llm


def get_search() -> WebSearchPort:
    global _search
    if _search is None:
        _search = _guard_paid(build_search(), "aisa.search")
    return _search


def get_events() -> EventLog:
    return _events


def get_audit() -> AuditLog:
    return _audit


def get_pii() -> PIIFilter:
    return _pii


def get_billing() -> StripeBilling:
    # Fresh per request: tests toggle STRIPE_SECRET_KEY via env.
    return StripeBilling()


def get_brokerage() -> BrokeragePort:
    global _brokerage
    if _brokerage is None:
        _brokerage = MockBrokerage()
    return _brokerage


def get_orchestrator(
    store: InMemoryStore = Depends(get_store),
    market: MarketDataPort = Depends(get_market_port),
    llm: LLMPort = Depends(get_llm),
    search: WebSearchPort = Depends(get_search),
    events: EventLog = Depends(get_events),
    audit: AuditLog = Depends(get_audit),
) -> Orchestrator:
    return Orchestrator(
        store=store, market=market, llm=llm, search=search, events=events, audit=audit
    )


def get_executor(
    store: InMemoryStore = Depends(get_store),
    market: MarketDataPort = Depends(get_market_port),
    events: EventLog = Depends(get_events),
    audit: AuditLog = Depends(get_audit),
) -> InvestmentExecutor:
    return InvestmentExecutor(store, market, events, audit)


def get_learning(
    store: InMemoryStore = Depends(get_store),
    llm: LLMPort = Depends(get_llm),
    events: EventLog = Depends(get_events),
) -> LearningAgent:
    return LearningAgent(llm, store, events)


def reset_state() -> None:
    """Test hook: fresh store, market, ports, events, audit, brokerage, credits."""
    global _store, _market, _market_port, _llm, _search, _events, _audit, _brokerage
    _store = InMemoryStore()
    _market = None
    _market_port = None
    _llm = None
    _search = None
    _events = EventLog()
    _audit = AuditLog()
    _brokerage = None
    reset_metering()


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
    return {"status": "ok", "version": "0.2.1"}


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
    pii: PIIFilter = Depends(get_pii),
) -> dict:
    text = pii.redact((body.text or "").strip())
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
    except CreditsExhausted:
        raise _credits_402() from None
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
    except CreditsExhausted:
        raise _credits_402() from None
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
    except CreditsExhausted:
        raise _credits_402() from None
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


# ------------------------------------------------- v2.1 routes: harness, gate, billing


def _credits_402() -> HTTPException:
    """402 when a paid provider call was refused (empty balance or cap).

    The agent never silently overspends: instead of degrading to a wrong
    answer, the request fails with a top-up path.
    """
    return HTTPException(
        status_code=402,
        detail={
            "message": "credits exhausted: agents cannot make paid provider calls",
            "top_up": "/api/billing/credits/checkout",
            "packs": "/api/billing/credits/packs",
        },
    )


class HarnessRunRequest(BaseModel):
    text: str
    account_id: str | None = None


class ProposeRequest(BaseModel):
    account_id: str
    allocations: list[AllocationInput]


class ConfirmRequest(BaseModel):
    approval_id: str
    approved: bool


class ProfileUpdateRequest(BaseModel):
    risk: str | None = None
    horizon_years: float | None = None
    preferences: dict | None = None


class CheckoutRequest(BaseModel):
    price_id: str
    success_url: str
    cancel_url: str
    customer_email: str | None = None
    mode: str = "subscription"


class BrokerageOrderRequest(BaseModel):
    symbol: str
    qty: str  # decimal string
    side: str  # "buy" | "sell"


def _allocations_or_400(items: list[AllocationInput]) -> list[Allocation]:
    allocations: list[Allocation] = []
    for item in items:
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
    return allocations


@app.get("/api/analyze/{symbol}")
async def analyze_symbol(
    symbol: str,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> dict:
    try:
        analysis = await orchestrator.analyze(symbol)
    except CreditsExhausted:
        raise _credits_402() from None
    except ValueError as exc:
        if "unknown symbol" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "symbol": analysis.symbol,
        "price": str(analysis.price),
        "verdict": analysis.verdict,
        "risk_flags": analysis.risk_flags,
        "summary_plain": analysis.summary_plain,
    }


@app.post("/api/harness/run")
async def harness_run(
    body: HarnessRunRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> dict:
    if not (body.text or "").strip():
        raise HTTPException(status_code=400, detail="text is required")
    try:
        result = await orchestrator.run(
            RunRequest(text=body.text, account_id=body.account_id)
        )
    except CreditsExhausted:
        raise _credits_402() from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "run_id": result.run_id,
        "intent": result.intent,
        "confidence": result.confidence,
        "requires_human": result.requires_human,
        "human_question": result.human_question,
        "results": result.results,
        "checkpoints": result.checkpoints,
        "error": result.error,
    }


@app.post("/api/executor/propose")
async def executor_propose(
    body: ProposeRequest,
    executor: InvestmentExecutor = Depends(get_executor),
) -> dict:
    allocations = _allocations_or_400(body.allocations)
    try:
        approval = await executor.propose(body.account_id, allocations)
    except CreditsExhausted:
        raise _credits_402() from None
    except ValueError as exc:
        if "account not found" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "approval_id": approval.id,
        "status": approval.status,
        "trades": approval.trades,
        "total_usd": str(approval.total_usd),
        "created_at": approval.created_at.isoformat(),
    }


@app.post("/api/executor/confirm")
async def executor_confirm(
    body: ConfirmRequest,
    executor: InvestmentExecutor = Depends(get_executor),
    store: InMemoryStore = Depends(get_store),
) -> dict:
    approval = store.get_approval(body.approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="approval not found")
    # The request carries no account id; bill the approval's account.
    try:
        with account_context(approval.account_id):
            return await executor.confirm(body.approval_id, body.approved)
    except CreditsExhausted:
        raise _credits_402() from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/audit")
def get_audit_log(
    account_id: str | None = None,
    action: str | None = None,
    limit: int = 100,
    audit: AuditLog = Depends(get_audit),
) -> dict:
    entries = audit.list(
        account_id=account_id, action=action, limit=max(limit, 1)
    )
    return {
        "entries": [
            {
                "id": e.id,
                "actor": e.actor,
                "action": e.action,
                "account_id": e.account_id,
                "outcome": e.outcome,
                "details": e.details,
                "created_at": e.created_at.isoformat(),
            }
            for e in entries
        ]
    }


@app.post("/api/billing/checkout")
def billing_checkout(
    body: CheckoutRequest,
    billing: StripeBilling = Depends(get_billing),
) -> dict:
    # Stripe moves PRODUCT money (subscriptions), never market orders.
    try:
        return billing.create_checkout_session(
            price_id=body.price_id,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            customer_email=body.customer_email,
            mode=body.mode,
        )
    except BillingNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class CreditsCheckoutRequest(BaseModel):
    account_id: str
    pack_id: str
    success_url: str
    cancel_url: str
    customer_email: str | None = None


@app.post("/api/billing/credits/checkout")
def credits_checkout(
    body: CreditsCheckoutRequest,
    billing: StripeBilling = Depends(get_billing),
    store: InMemoryStore = Depends(get_store),
) -> dict:
    """Sell a credit pack: Stripe takes the card, the webhook credits the ledger.

    Credits are what agents spend on paid AIsa calls (1 credit = $0.001).
    """
    if store.get_account(body.account_id) is None:
        raise HTTPException(status_code=404, detail="account not found")
    try:
        return billing.create_credits_checkout_session(
            pack_id=body.pack_id,
            account_id=body.account_id,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            customer_email=body.customer_email,
        )
    except BillingNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/billing/credits/packs")
def credits_packs() -> dict:
    """The credit packs on sale. Public catalog — no Stripe key needed."""
    return {
        "packs": [
            {
                "pack_id": pack.pack_id,
                "usd": f"{pack.usd_cents / 100:.2f}",
                "credits": pack.credits,
            }
            for pack in CREDIT_PACKS.values()
        ]
    }


@app.get("/api/billing/credits/balance")
def credits_balance(
    account_id: str, store: InMemoryStore = Depends(get_store)
) -> dict:
    if store.get_account(account_id) is None:
        raise HTTPException(status_code=404, detail="account not found")
    balance = get_ledger().balance(account_id)
    return {
        "account_id": account_id,
        "balance_credits": balance,
        "balance_usd": str(credits_to_usd(balance)),
    }


def _fulfill_credits_event(event: dict, audit: AuditLog) -> None:
    """Fulfill a credit-pack purchase: idempotent ledger credit + audit entry.

    ``checkout.session.completed`` with ``metadata.kind == "credits"``.
    Everything else (subscriptions, etc.) is left to the subscription flow.
    """
    if event.get("type") != "checkout.session.completed":
        return
    obj = (event.get("data") or {}).get("object") or {}
    meta = obj.get("metadata") or {}
    if meta.get("kind") != "credits":
        return
    account_id = meta.get("account_id")
    try:
        credits = int(meta.get("credits") or 0)
    except (TypeError, ValueError):
        credits = 0
    if not account_id or credits <= 0:
        return
    entry = get_ledger().credit_unique(
        str(obj.get("id") or ""),
        account_id,
        credits,
        tool="stripe",
        meta={"pack_id": meta.get("pack_id"), "session_id": obj.get("id")},
    )
    if entry is not None:
        audit.append(
            actor="billing",
            action="credits.purchase",
            account_id=account_id,
            details={
                "credits": credits,
                "credits_usd": str(credits_to_usd(credits)),
                "pack_id": meta.get("pack_id"),
                "entry_id": entry.id,
            },
        )


@app.post("/api/billing/webhook")
async def billing_webhook(
    request: Request,
    billing: StripeBilling = Depends(get_billing),
    audit: AuditLog = Depends(get_audit),
) -> dict:
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = billing.handle_webhook(
            payload=payload, signature=signature, webhook_secret=None
        )
    except BillingNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Credit-pack purchases fulfill into the credits ledger (idempotent);
    # subscription events keep flowing through the subscription skeleton.
    _fulfill_credits_event(event, audit)
    return {"received": True, "type": event.get("type")}


@app.get("/api/brokerage/account")
async def brokerage_account(
    brokerage: BrokeragePort = Depends(get_brokerage),
) -> dict:
    account = await brokerage.get_account()
    return {
        "cash": str(account.cash),
        "portfolio_value": str(account.portfolio_value),
        "currency": account.currency,
        "live": account.live,
    }


@app.post("/api/brokerage/orders")
async def brokerage_submit_order(
    body: BrokerageOrderRequest,
    brokerage: BrokeragePort = Depends(get_brokerage),
) -> dict:
    try:
        side = OrderSide(body.side.lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="side must be 'buy' or 'sell'"
        ) from exc
    try:
        qty = Decimal(body.qty)
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail="qty must be a decimal number"
        ) from exc
    try:
        order = await brokerage.submit_order(body.symbol, qty, side)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "id": order.id,
        "symbol": order.symbol,
        "qty": str(order.qty),
        "side": order.side.value,
        "status": order.status,
        "filled_price": str(order.filled_price) if order.filled_price else None,
    }


@app.get("/api/brokerage/orders/{order_id}")
async def brokerage_get_order(
    order_id: str,
    brokerage: BrokeragePort = Depends(get_brokerage),
) -> dict:
    order = await brokerage.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return {
        "id": order.id,
        "symbol": order.symbol,
        "qty": str(order.qty),
        "side": order.side.value,
        "status": order.status,
        "filled_price": str(order.filled_price) if order.filled_price else None,
    }


@app.get("/api/profile/{account_id}")
def get_profile(
    account_id: str,
    learning: LearningAgent = Depends(get_learning),
    store: InMemoryStore = Depends(get_store),
) -> dict:
    if store.get_account(account_id) is None:
        raise HTTPException(status_code=404, detail="account not found")
    profile = learning.get_profile(account_id)
    return {
        "account_id": profile.account_id,
        "risk": profile.risk,
        "horizon_years": profile.horizon_years,
        "preferences": profile.preferences,
    }


@app.put("/api/profile/{account_id}")
def update_profile(
    account_id: str,
    body: ProfileUpdateRequest,
    learning: LearningAgent = Depends(get_learning),
    store: InMemoryStore = Depends(get_store),
    pii: PIIFilter = Depends(get_pii),
) -> dict:
    if store.get_account(account_id) is None:
        raise HTTPException(status_code=404, detail="account not found")
    try:
        profile = learning.update_profile(
            account_id,
            risk=body.risk,
            horizon_years=body.horizon_years,
            preferences=body.preferences,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "account_id": profile.account_id,
        "risk": profile.risk,
        "horizon_years": profile.horizon_years,
        "preferences": profile.preferences,
    }
