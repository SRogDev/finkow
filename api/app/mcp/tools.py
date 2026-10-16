"""The twelve MCP tools: thin, honest wrappers over the backend domain.

Each tool takes ``(ctx, client, *, mode, **params)`` and returns a pydantic
output model carrying ``mode``/``virtual`` labels. Tool functions assume
dispatch() already authenticated, rate-limited, and permission-checked;
they re-check the mode so direct calls are safe too.

- Read tools (``read`` permission): portfolio, positions, transactions,
  performance, market data, opportunities, asset analysis, portfolio
  analysis, activity history, action validation, order status.
- The single mutating tool (``read+propose``): ``prepare_investment_proposal``
  — dry-run propose path only, DRAFT orders, ``pending_authorization``.

There is no execution tool on purpose: real execution does not exist in
this build, and paper submission stays behind the human confirmation gate.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from app.agents.planner import Allocation
from app.main import (
    DEFAULT_WATCHLIST,
    _portfolio_view_port,
    _serialize_order,
    _serialize_portfolio,
)
from app.market import MarketDataError
from app.mcp import auth as mcp_auth
from app.mcp import errors as mcp_errors
from app.mcp import models as mcp_models
from app.mcp.context import (
    PERM_PROPOSE,
    PERM_READ,
    McpContext,
    account_for,
    require_experimental,
)
from app.modes import Mode
from app.money import cash_str, to_qty
from app.orders import RiskLimits
from app.ports import ProviderError

PENDING_AUTHORIZATION = "pending_authorization"


def _labels(mode: Mode) -> dict:
    return {"mode": mode.value, "virtual": mode is Mode.EXPERIMENTAL}


def _coerce_mode(mode) -> Mode:
    return require_experimental(mode if isinstance(mode, str) else mode.value)


async def get_portfolio(
    ctx: McpContext,
    client: mcp_auth.McpClient,
    *,
    mode: str | Mode = "experimental",
    account_id: str,
) -> mcp_models.PortfolioOut:
    """Read-only: full portfolio valuation with virtual-money labels."""
    m = _coerce_mode(mode)
    account = account_for(ctx, client, account_id)
    pv = await _portfolio_view_port(account.id, ctx.store, ctx.market)
    data = _serialize_portfolio(pv)
    return mcp_models.PortfolioOut(
        account_id=data["account_id"],
        cash=data["cash"],
        initial_cash=data["initial_cash"],
        total_value=data["total_value"],
        total_return=data["total_return"],
        total_return_pct=data["total_return_pct"],
        allocation=data["allocation"],
        as_of=data["as_of"],
        positions=[mcp_models.PositionOut(**p) for p in data["positions"]],
        **_labels(m),
    )


async def get_positions(
    ctx: McpContext,
    client: mcp_auth.McpClient,
    *,
    mode: str | Mode = "experimental",
    account_id: str,
) -> mcp_models.PositionsOut:
    """Read-only: the account's positions, valued at the latest quotes."""
    m = _coerce_mode(mode)
    account = account_for(ctx, client, account_id)
    pv = await _portfolio_view_port(account.id, ctx.store, ctx.market)
    data = _serialize_portfolio(pv)
    return mcp_models.PositionsOut(
        account_id=account.id,
        positions=[mcp_models.PositionOut(**p) for p in data["positions"]],
        **_labels(m),
    )


async def get_transaction_history(
    ctx: McpContext,
    client: mcp_auth.McpClient,
    *,
    mode: str | Mode = "experimental",
    account_id: str,
    limit: int = 100,
) -> mcp_models.TransactionHistoryOut:
    """Read-only: chronological transactions with explicit statuses."""
    m = _coerce_mode(mode)
    account = account_for(ctx, client, account_id)
    txns = ctx.store.list_transactions(account.id)[: max(limit, 1)]
    return mcp_models.TransactionHistoryOut(
        account_id=account.id,
        transactions=[
            mcp_models.TransactionOut(
                id=t.id,
                symbol=t.symbol,
                side=t.side,
                quantity=str(t.qty),
                price=str(t.price),
                cash_delta=str(t.cash_delta),
                realized_pnl=str(t.realized_pnl)
                if t.realized_pnl is not None
                else None,
                order_id=t.order_id,
                status=t.status.value,
                simulated=t.simulated,
                created_at=t.created_at.isoformat(),
            )
            for t in txns
        ],
        **_labels(m),
    )


async def get_portfolio_performance(
    ctx: McpContext,
    client: mcp_auth.McpClient,
    *,
    mode: str | Mode = "experimental",
    account_id: str,
) -> mcp_models.PortfolioPerformanceOut:
    """Read-only: performance from portfolio snapshots (virtual money)."""
    m = _coerce_mode(mode)
    account = account_for(ctx, client, account_id)
    snaps = ctx.store.list_snapshots(account.id)
    if not snaps:
        return mcp_models.PortfolioPerformanceOut(
            account_id=account.id, snapshots=0, **_labels(m)
        )
    first, last = snaps[0], snaps[-1]
    total_return = last.total_value - first.total_value
    pct = (
        (total_return / first.total_value * Decimal("100"))
        if first.total_value
        else Decimal("0")
    )
    return mcp_models.PortfolioPerformanceOut(
        account_id=account.id,
        snapshots=len(snaps),
        first_value=cash_str(first.total_value),
        first_at=first.created_at.isoformat(),
        last_value=cash_str(last.total_value),
        last_at=last.created_at.isoformat(),
        total_return=cash_str(total_return),
        total_return_pct=f"{pct:.2f}",
        **_labels(m),
    )


async def get_market_data(
    ctx: McpContext,
    client: mcp_auth.McpClient,
    *,
    mode: str | Mode = "experimental",
    symbol: str,
) -> mcp_models.QuoteOut:
    """Read-only: a quote from the primary market-data provider.

    The free live fallback chain is disabled on the MCP path: an unknown
    symbol is a NOT_FOUND error, never a surprise external call. The
    ``provider`` field names the source (``mock`` in this build).
    """
    m = _coerce_mode(mode)
    sym = (symbol or "").strip().upper()
    if not sym:
        raise mcp_errors.McpError(
            mcp_errors.INVALID_INPUT, "symbol is required"
        )
    quote = await ctx.market.get_quote(sym)
    return mcp_models.QuoteOut(
        symbol=quote.symbol,
        price=str(quote.price),
        currency=quote.currency,
        as_of=quote.as_of.isoformat(),
        provider=quote.provider,
        stale=quote.stale,
        **_labels(m),
    )


async def search_investment_opportunities(
    ctx: McpContext,
    client: mcp_auth.McpClient,
    *,
    mode: str | Mode = "experimental",
    symbols: str = "",
    goal_id: str | None = None,
) -> mcp_models.OpportunitiesOut:
    """Read-only: ranked, reasoned opportunities from the opportunity radar.

    Present these as possibilities with evidence and risks — never as
    guaranteed outcomes.
    """
    m = _coerce_mode(mode)
    watch: list[str] = []
    if symbols:
        watch = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    elif goal_id:
        goal = ctx.store.get_goal(goal_id)
        if goal is None:
            raise mcp_errors.McpError(
                mcp_errors.NOT_FOUND, f"goal not found: {goal_id}"
            )
        account_for(ctx, client, goal.account_id)
        plan = ctx.store.get_plan(goal_id)
        if plan:
            watch = [str(a["symbol"]).upper() for a in plan["allocations"]]
    if not watch:
        watch = list(DEFAULT_WATCHLIST)
    opportunities = await ctx.radar.scan(watch)
    return mcp_models.OpportunitiesOut(
        opportunities=[
            mcp_models.OpportunityOut(
                symbol=o.symbol,
                score=o.score,
                price=str(o.price),
                reasoning=o.reasoning,
            )
            for o in opportunities
        ],
        provider=ctx.market.name,
        **_labels(m),
    )


async def analyze_asset(
    ctx: McpContext,
    client: mcp_auth.McpClient,
    *,
    mode: str | Mode = "experimental",
    symbol: str,
) -> mcp_models.AssetAnalysisOut:
    """Read-only: fundamentals, valuation sanity, and risk flags."""
    m = _coerce_mode(mode)
    sym = (symbol or "").strip().upper()
    if not sym:
        raise mcp_errors.McpError(
            mcp_errors.INVALID_INPUT, "symbol is required"
        )
    try:
        analysis = await ctx.orchestrator.analyze(sym)
    except ValueError as exc:
        raise mcp_errors.McpError(mcp_errors.NOT_FOUND, str(exc)) from exc
    return mcp_models.AssetAnalysisOut(
        symbol=analysis.symbol,
        price=str(analysis.price),
        verdict=analysis.verdict,
        risk_flags=list(analysis.risk_flags),
        summary_plain=analysis.summary_plain,
        **_labels(m),
    )


async def analyze_portfolio(
    ctx: McpContext,
    client: mcp_auth.McpClient,
    *,
    mode: str | Mode = "experimental",
    account_id: str,
) -> mcp_models.PortfolioAnalysisOut:
    """Read-only: portfolio diagnostics computed from actual numbers.

    Allocation concentration, cash weight, unrealized totals, and a
    plain-language summary built only from the computed figures — no
    invented insight.
    """
    m = _coerce_mode(mode)
    account = account_for(ctx, client, account_id)
    pv = await _portfolio_view_port(account.id, ctx.store, ctx.market)
    data = _serialize_portfolio(pv)
    weights = {k: Decimal(v) for k, v in data["allocation"].items()}
    cash_w = weights.get("CASH", Decimal("0"))
    pos_weights = {k: v for k, v in weights.items() if k != "CASH"}
    top = max(pos_weights.items(), key=lambda kv: kv[1], default=(None, None))
    unrealized = sum(
        (Decimal(p["unrealized_pnl"]) for p in data["positions"]), Decimal("0")
    )
    summary = (
        f"Experimental (virtual-money) portfolio {account.id}: total value "
        f"{data['total_value']} USD across {len(data['positions'])} positions; "
        f"cash weight {cash_w:.4f}; "
        + (
            f"largest position {top[0]} at {top[1]:.4f}; "
            if top[0]
            else "no invested positions; "
        )
        + f"unrealized P&L {unrealized:.2f} USD; total return "
        f"{data['total_return']} USD ({data['total_return_pct']}%)."
    )
    return mcp_models.PortfolioAnalysisOut(
        account_id=account.id,
        total_value=data["total_value"],
        cash=data["cash"],
        cash_weight=f"{cash_w:.4f}",
        positions_count=len(data["positions"]),
        top_position=top[0],
        top_position_weight=f"{top[1]:.4f}" if top[0] else None,
        unrealized_pnl_total=f"{unrealized:.2f}",
        total_return=data["total_return"],
        total_return_pct=data["total_return_pct"],
        summary_plain=summary,
        **_labels(m),
    )


async def get_activity_history(
    ctx: McpContext,
    client: mcp_auth.McpClient,
    *,
    mode: str | Mode = "experimental",
    agent: str | None = None,
    limit: int = 50,
) -> mcp_models.ActivityHistoryOut:
    """Read-only: the agent activity/event log (newest last)."""
    m = _coerce_mode(mode)
    events = ctx.events.list(agent=agent, limit=max(limit, 1))
    return mcp_models.ActivityHistoryOut(
        events=[
            mcp_models.ActivityEventOut(
                id=e.id,
                agent=e.agent,
                kind=e.kind,
                payload=dict(e.payload),
                created_at=e.created_at.isoformat(),
            )
            for e in events
        ],
        **_labels(m),
    )


async def prepare_investment_proposal(
    ctx: McpContext,
    client: mcp_auth.McpClient,
    *,
    mode: str | Mode = "experimental",
    account_id: str,
    allocations: list[dict],
    idempotency_key: str | None = None,
) -> mcp_models.ProposalOut:
    """DRAFT ONLY (requires 'propose' permission): compute the trades that
    would move the portfolio toward target allocations WITHOUT moving any
    money, store a pending approval, and create DRAFT orders.

    Returns ``status: "pending_authorization"``. A HUMAN must confirm the
    proposal through the Finkow app (or a pre-authorized policy) before
    anything is submitted — MCP exposes no execution tool, and this tool
    never claims execution. Draft orders are simulated (virtual money).
    """
    m = _coerce_mode(mode)
    if not client.can(PERM_PROPOSE):
        raise mcp_errors.McpError(
            mcp_errors.PERMISSION_DENIED,
            "prepare_investment_proposal requires 'propose' permission; "
            "this API key is read-only. Permissions are operator "
            "configuration — an agent cannot grant itself permissions.",
        )
    account = account_for(ctx, client, account_id)
    parsed = _parse_allocations(allocations)

    if idempotency_key:
        seen = ctx.idempotency.get(idempotency_key)
        if seen is not None:
            approval = ctx.store.get_approval(seen)
            if approval is not None:
                return _proposal_out(ctx, approval, m, idempotent_replay=True)

    approval = await ctx.executor.propose(account.id, parsed)
    if idempotency_key:
        ctx.idempotency[idempotency_key] = approval.id
    return _proposal_out(ctx, approval, m)


def _parse_allocations(allocations: list[dict]) -> list[Allocation]:
    parsed: list[Allocation] = []
    if not allocations:
        raise mcp_errors.McpError(
            mcp_errors.INVALID_INPUT, "at least one allocation is required"
        )
    for item in allocations:
        try:
            symbol = str(item.get("symbol", "")).strip().upper()
            weight = Decimal(str(item.get("weight", "")))
        except (InvalidOperation, ValueError, TypeError, AttributeError) as exc:
            raise mcp_errors.McpError(
                mcp_errors.INVALID_INPUT,
                f"invalid allocation {item!r}: symbol and decimal weight required",
            ) from exc
        if not symbol:
            raise mcp_errors.McpError(
                mcp_errors.INVALID_INPUT, "allocation symbol is required"
            )
        if weight <= 0 or weight > 1:
            raise mcp_errors.McpError(
                mcp_errors.INVALID_INPUT,
                f"weight must be between 0 and 1, got {item.get('weight')!r}",
            )
        parsed.append(Allocation(symbol, weight, ""))
    return parsed


def _proposal_out(
    ctx: McpContext, approval, mode: Mode, idempotent_replay: bool = False
) -> mcp_models.ProposalOut:
    expires_at = approval.created_at + timedelta(minutes=15)
    return mcp_models.ProposalOut(
        approval_id=approval.id,
        account_id=approval.account_id,
        status=PENDING_AUTHORIZATION,
        trades=[
            mcp_models.ProposedTradeOut(
                symbol=t["symbol"],
                side=t["side"],
                qty=t["qty"],
                est_price=t["est_price"],
                est_value=t["est_value"],
            )
            for t in approval.trades
        ],
        total_usd=str(approval.total_usd),
        created_at=approval.created_at.isoformat(),
        expires_at=expires_at.isoformat(),
        idempotent_replay=idempotent_replay,
        requires_approval=(
            "A human must confirm this proposal through the Finkow app before "
            "anything is submitted; the proposal expires 15 minutes after "
            "creation. MCP cannot execute trades — this is a draft only."
        ),
        **_labels(mode),
    )


async def validate_investment_action(
    ctx: McpContext,
    client: mcp_auth.McpClient,
    *,
    mode: str | Mode = "experimental",
    account_id: str,
    symbol: str,
    side: str,
    quantity: str,
) -> mcp_models.ValidationOut:
    """Read-only dry validation: would this action pass the risk controls?

    Checks ownership, symbol availability, quantity sanity, and the
    per-trade USD limit — without creating orders or moving money.
    Passing validation is NOT a guarantee the action would execute.
    """
    m = _coerce_mode(mode)
    account = account_for(ctx, client, account_id)
    sym = (symbol or "").strip().upper()
    reasons: list[str] = []
    est_value: Decimal | None = None

    side_norm = (side or "").lower()
    if side_norm not in ("buy", "sell"):
        reasons.append(f"side must be 'buy' or 'sell', got {side!r}")
    try:
        qty = to_qty(Decimal(str(quantity)))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise mcp_errors.McpError(
            mcp_errors.INVALID_INPUT,
            f"quantity must be a decimal number, got {quantity!r}",
        ) from exc
    if qty <= 0:
        reasons.append("quantity must be positive")
    if not sym:
        reasons.append("symbol is required")
    quote = None
    if sym:
        try:
            quote = await ctx.market.get_quote(sym)
        except (MarketDataError, ProviderError):
            reasons.append(f"no market data available for symbol {sym!r}")
    if quote is not None and qty > 0:
        est_value = quote.price * qty
        limits = RiskLimits()
        if est_value > limits.max_trade_usd:
            reasons.append(
                f"estimated value {est_value:.2f} USD exceeds the per-trade "
                f"limit of {limits.max_trade_usd} USD"
            )
    allowed = not reasons
    if allowed:
        reasons.append(
            "dry validation passed: within risk controls, symbol priced, "
            "inputs sane. Not a guarantee of execution."
        )
    return mcp_models.ValidationOut(
        account_id=account.id,
        symbol=sym,
        side=side_norm,
        quantity=str(qty) if qty > 0 else str(quantity),
        est_value=f"{est_value:.2f}" if est_value is not None else None,
        allowed=allowed,
        reasons=reasons,
        **_labels(m),
    )


async def get_order_status(
    ctx: McpContext,
    client: mcp_auth.McpClient,
    *,
    mode: str | Mode = "experimental",
    order_id: str | None = None,
    approval_id: str | None = None,
) -> mcp_models.OrderStatusOut:
    """Read-only: the status of an order, or of a proposal approval.

    Pass exactly one of ``order_id`` / ``approval_id``. A pending proposal
    reports ``status: "pending_authorization"`` with its DRAFT orders
    (simulated, never submitted until the human confirms).
    """
    m = _coerce_mode(mode)
    if bool(order_id) == bool(approval_id):
        raise mcp_errors.McpError(
            mcp_errors.INVALID_INPUT,
            "pass exactly one of 'order_id' or 'approval_id'",
        )
    if order_id:
        order = ctx.store.get_order(order_id)
        if order is None:
            raise mcp_errors.McpError(
                mcp_errors.NOT_FOUND, f"order not found: {order_id}"
            )
        account_for(ctx, client, order.account_id)
        return mcp_models.OrderStatusOut(
            order_id=order.id,
            status=_serialize_order(order)["status"],
            orders=[_serialize_order(order)],
            **_labels(m),
        )
    approval = ctx.store.get_approval(approval_id or "")
    if approval is None:
        raise mcp_errors.McpError(
            mcp_errors.NOT_FOUND, f"approval not found: {approval_id}"
        )
    account_for(ctx, client, approval.account_id)
    status = (
        PENDING_AUTHORIZATION if approval.status == "pending" else approval.status
    )
    draft_orders = [
        _serialize_order(o)
        for o in ctx.orders.list_for_approval(approval.account_id, approval.id)
    ]
    return mcp_models.OrderStatusOut(
        approval_id=approval.id,
        status=status,
        orders=draft_orders,
        total_usd=str(approval.total_usd),
        created_at=approval.created_at.isoformat(),
        expires_at=(approval.created_at + timedelta(minutes=15)).isoformat(),
        **_labels(m),
    )


# Tool registry: name → (required permission, implementation).
TOOLS: dict[str, tuple[str, object]] = {
    "get_portfolio": (PERM_READ, get_portfolio),
    "get_positions": (PERM_READ, get_positions),
    "get_transaction_history": (PERM_READ, get_transaction_history),
    "get_portfolio_performance": (PERM_READ, get_portfolio_performance),
    "get_market_data": (PERM_READ, get_market_data),
    "search_investment_opportunities": (PERM_READ, search_investment_opportunities),
    "analyze_asset": (PERM_READ, analyze_asset),
    "analyze_portfolio": (PERM_READ, analyze_portfolio),
    "get_activity_history": (PERM_READ, get_activity_history),
    "prepare_investment_proposal": (PERM_PROPOSE, prepare_investment_proposal),
    "validate_investment_action": (PERM_READ, validate_investment_action),
    "get_order_status": (PERM_READ, get_order_status),
}
