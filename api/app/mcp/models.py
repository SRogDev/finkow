"""Strict pydantic models for MCP tool inputs and structured outputs.

Every financial response carries ``mode`` (always ``"experimental"`` — the
MCP surface rejects real mode) and ``virtual: true``, so no agent can
mistake simulated state for real money.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Envelope(BaseModel):
    """Base for every tool response: mode honesty in every payload."""

    mode: str = Field(
        default="experimental",
        description="Operating mode of the returned state. MCP is "
        "experimental-only; real mode is rejected.",
    )
    virtual: bool = Field(
        default=True,
        description="True: all values are simulated/virtual money, never real.",
    )


class AllocationInput(BaseModel):
    symbol: str = Field(description="Ticker symbol, e.g. AAPL.")
    weight: str = Field(description="Target weight as a decimal string, 0 < w <= 1.")


class PositionOut(BaseModel):
    symbol: str
    quantity: str
    avg_cost: str
    price: str
    market_value: str
    unrealized_pnl: str
    unrealized_pnl_pct: str
    stale: bool


class PortfolioOut(Envelope):
    account_id: str
    cash: str
    initial_cash: str
    total_value: str
    total_return: str
    total_return_pct: str
    allocation: dict[str, str]
    as_of: str
    positions: list[PositionOut]


class PositionsOut(Envelope):
    account_id: str
    positions: list[PositionOut]


class TransactionOut(BaseModel):
    id: str
    symbol: str
    side: str
    quantity: str
    price: str
    cash_delta: str
    realized_pnl: str | None
    order_id: str | None
    status: str
    simulated: bool
    created_at: str


class TransactionHistoryOut(Envelope):
    account_id: str
    transactions: list[TransactionOut]


class PortfolioPerformanceOut(Envelope):
    account_id: str
    snapshots: int
    first_value: str | None = None
    first_at: str | None = None
    last_value: str | None = None
    last_at: str | None = None
    total_return: str | None = None
    total_return_pct: str | None = None


class QuoteOut(Envelope):
    symbol: str
    price: str
    currency: str
    as_of: str
    provider: str
    stale: bool


class OpportunityOut(BaseModel):
    symbol: str
    score: float
    price: str
    reasoning: str


class OpportunitiesOut(Envelope):
    opportunities: list[OpportunityOut]
    provider: str


class AssetAnalysisOut(Envelope):
    symbol: str
    price: str
    verdict: str
    risk_flags: list[str]
    summary_plain: str


class PortfolioAnalysisOut(Envelope):
    account_id: str
    total_value: str
    cash: str
    cash_weight: str
    positions_count: int
    top_position: str | None
    top_position_weight: str | None
    unrealized_pnl_total: str
    total_return: str
    total_return_pct: str
    summary_plain: str


class ActivityEventOut(BaseModel):
    id: str
    agent: str
    kind: str
    payload: dict
    created_at: str


class ActivityHistoryOut(Envelope):
    events: list[ActivityEventOut]


class ProposedTradeOut(BaseModel):
    symbol: str
    side: str
    qty: str
    est_price: str
    est_value: str


class ProposalOut(Envelope):
    approval_id: str
    account_id: str
    status: str = Field(
        description="Always 'pending_authorization': the human confirmation "
        "gate must approve before anything moves. MCP has no execution tool."
    )
    trades: list[ProposedTradeOut]
    total_usd: str
    created_at: str
    expires_at: str
    idempotent_replay: bool = False
    requires_approval: str = Field(
        description="What the human must do to authorize this proposal."
    )


class ValidationOut(Envelope):
    account_id: str
    symbol: str
    side: str
    quantity: str
    est_value: str | None
    allowed: bool
    reasons: list[str] = Field(
        description="Why the action is allowed or denied. Never a guarantee "
        "of future execution."
    )


class OrderStatusOut(Envelope):
    approval_id: str | None = None
    order_id: str | None = None
    status: str = Field(
        description="Order lifecycle status, or 'pending_authorization' for "
        "a proposal awaiting the human gate. Never a false executed claim."
    )
    orders: list[dict] = Field(
        default_factory=list,
        description="Draft orders attached to the approval (simulated, "
        "never submitted until the human confirms).",
    )
    total_usd: str | None = None
    created_at: str | None = None
    expires_at: str | None = None
