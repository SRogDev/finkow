"""Finkow MCP server entry point: stdio transport over the MCP SDK.

Run: ``uv run python -m app.mcp.server`` (from ``api/``).

Configuration (environment):
- ``FINKOW_MCP_API_KEYS``: comma-separated ``<secret>[:<perms>[:<user_id>]]``
  entries; ``<perms>`` is ``read`` (default) or ``read+propose``. No keys
  configured → every call is rejected.
- ``FINKOW_MCP_RATE_LIMIT_PER_MIN``: per-key budget (default 60).
- ``FINKOW_STORE`` / ``FINKOW_DB_PATH``: storage backend, as in the REST app.

Every tool takes an ``api_key`` argument (stdio has no headers). Failures
are MCP tool results with ``isError: true`` and a JSON
``{"code", "message"}`` payload; codes are documented in
``app/mcp/errors.py`` and ``docs/MCP_SPEC.md``.
"""

from __future__ import annotations

import json
import logging

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from app.mcp import errors as mcp_errors
from app.mcp import models as mcp_models
from app.mcp.context import McpContext, dispatch

log = logging.getLogger("finkow.mcp.server")

server = MCPServer("finkow-mcp")
_CTX: McpContext | None = None


def _ctx() -> McpContext:
    global _CTX
    if _CTX is None:
        _CTX = McpContext.build()
    return _CTX


async def _run(tool_name: str, args: dict):
    """Dispatch through the central gate; translate McpError to ToolError."""
    try:
        return await dispatch(_ctx(), tool_name, args)
    except mcp_errors.McpError as exc:
        raise ToolError(json.dumps(exc.payload())) from exc


API_KEY_FIELD = Field(description=(
    "MCP API key from FINKOW_MCP_API_KEYS. Authenticated per call with "
    "constant-time comparison. Never logged or echoed back."
))
MODE_FIELD = Field(
    default="experimental",
    description=(
        "Operating mode. MCP is experimental-only: 'real' is rejected. "
        "Every response labels mode and virtual explicitly."
    ),
)


@server.tool(structured_output=True, description=(
    "READ-ONLY (permission: read). Full portfolio valuation for an account: "
    "cash, positions valued at latest quotes, allocation, returns. All "
    "values are virtual/simulated money, labeled in every response."
))
async def get_portfolio(
    api_key: str = API_KEY_FIELD,
    account_id: str = Field(description="Account id."),
    mode: str = MODE_FIELD,
) -> mcp_models.PortfolioOut:
    return await _run("get_portfolio", {"api_key": api_key, "account_id": account_id, "mode": mode})


@server.tool(structured_output=True, description=(
    "READ-ONLY (permission: read). The account's positions valued at the "
    "latest quotes. Virtual money, labeled in every response."
))
async def get_positions(
    api_key: str = API_KEY_FIELD,
    account_id: str = Field(description="Account id."),
    mode: str = MODE_FIELD,
) -> mcp_models.PositionsOut:
    return await _run("get_positions", {"api_key": api_key, "account_id": account_id, "mode": mode})


@server.tool(structured_output=True, description=(
    "READ-ONLY (permission: read). Chronological transaction history with "
    "explicit per-transaction statuses and simulated markers."
))
async def get_transaction_history(
    api_key: str = API_KEY_FIELD,
    account_id: str = Field(description="Account id."),
    mode: str = MODE_FIELD,
    limit: int = Field(default=100, description="Max transactions, newest first."),
) -> mcp_models.TransactionHistoryOut:
    return await _run("get_transaction_history", {
        "api_key": api_key, "account_id": account_id, "mode": mode, "limit": limit})


@server.tool(structured_output=True, description=(
    "READ-ONLY (permission: read). Portfolio performance computed from "
    "stored snapshots (virtual money). Empty history returns zero snapshots."
))
async def get_portfolio_performance(
    api_key: str = API_KEY_FIELD,
    account_id: str = Field(description="Account id."),
    mode: str = MODE_FIELD,
) -> mcp_models.PortfolioPerformanceOut:
    return await _run("get_portfolio_performance", {
        "api_key": api_key, "account_id": account_id, "mode": mode})


@server.tool(structured_output=True, description=(
    "READ-ONLY (permission: read). A quote for a symbol from the primary "
    "market-data provider. The provider is named in the response ('mock' "
    "without an AIsa key — deterministic, zero live calls). Unknown "
    "symbols return NOT_FOUND; nothing is invented."
))
async def get_market_data(
    api_key: str = API_KEY_FIELD,
    symbol: str = Field(description="Ticker symbol, e.g. AAPL."),
    mode: str = MODE_FIELD,
) -> mcp_models.QuoteOut:
    return await _run("get_market_data", {"api_key": api_key, "symbol": symbol, "mode": mode})


@server.tool(structured_output=True, description=(
    "READ-ONLY (permission: read). Ranked investment opportunities with "
    "plain-language reasoning and cited evidence. Present these as "
    "possibilities with risks — never as guaranteed outcomes."
))
async def search_investment_opportunities(
    api_key: str = API_KEY_FIELD,
    symbols: str = Field(
        default="", description="Comma-separated tickers; defaults to the watchlist."),
    goal_id: str | None = Field(
        default=None, description="Optional goal id to scan its plan's allocations."),
    mode: str = MODE_FIELD,
) -> mcp_models.OpportunitiesOut:
    return await _run("search_investment_opportunities", {
        "api_key": api_key, "symbols": symbols, "goal_id": goal_id, "mode": mode})


@server.tool(structured_output=True, description=(
    "READ-ONLY (permission: read). Asset analysis: fundamentals, valuation "
    "sanity, verdict, and risk flags in plain language."
))
async def analyze_asset(
    api_key: str = API_KEY_FIELD,
    symbol: str = Field(description="Ticker symbol, e.g. AAPL."),
    mode: str = MODE_FIELD,
) -> mcp_models.AssetAnalysisOut:
    return await _run("analyze_asset", {"api_key": api_key, "symbol": symbol, "mode": mode})


@server.tool(structured_output=True, description=(
    "READ-ONLY (permission: read). Portfolio diagnostics computed from "
    "actual numbers: concentration, cash weight, unrealized P&L, and a "
    "plain-language summary. No invented insight. Virtual money, labeled."
))
async def analyze_portfolio(
    api_key: str = API_KEY_FIELD,
    account_id: str = Field(description="Account id."),
    mode: str = MODE_FIELD,
) -> mcp_models.PortfolioAnalysisOut:
    return await _run("analyze_portfolio", {
        "api_key": api_key, "account_id": account_id, "mode": mode})


@server.tool(structured_output=True, description=(
    "READ-ONLY (permission: read). The agent activity/event log (what the "
    "internal agents did, newest last)."
))
async def get_activity_history(
    api_key: str = API_KEY_FIELD,
    agent: str | None = Field(default=None, description="Filter by agent name."),
    mode: str = MODE_FIELD,
    limit: int = Field(default=50, description="Max events."),
) -> mcp_models.ActivityHistoryOut:
    return await _run("get_activity_history", {
        "api_key": api_key, "agent": agent, "mode": mode, "limit": limit})


@server.tool(structured_output=True, description=(
    "DRAFT ONLY (permission: read+propose). Compute the trades that would "
    "move the portfolio toward target allocations WITHOUT moving any money, "
    "store a pending approval, and create DRAFT orders. Returns "
    "status='pending_authorization'. BOUNDARY: a human must confirm the "
    "proposal through the Finkow app before anything is submitted; it "
    "expires after 15 minutes. MCP exposes NO execution tool and this tool "
    "NEVER claims execution. Draft orders are simulated (virtual money)."
))
async def prepare_investment_proposal(
    api_key: str = API_KEY_FIELD,
    account_id: str = Field(description="Account id."),
    allocations: list[dict] = Field(
        description="List of {'symbol': str, 'weight': str} (0 < w <= 1)."),
    mode: str = MODE_FIELD,
    idempotency_key: str | None = Field(
        default=None,
        description="Optional idempotency key: retries with the same key "
        "return the original proposal without creating duplicate drafts.",
    ),
) -> mcp_models.ProposalOut:
    return await _run("prepare_investment_proposal", {
        "api_key": api_key, "account_id": account_id, "allocations": allocations,
        "mode": mode, "idempotency_key": idempotency_key})


@server.tool(structured_output=True, description=(
    "READ-ONLY (permission: read). Dry validation: would this action pass "
    "the risk controls? Checks ownership, symbol pricing, quantity sanity, "
    "and the per-trade USD limit — without creating orders or moving money. "
    "Passing validation is NOT a guarantee of execution."
))
async def validate_investment_action(
    api_key: str = API_KEY_FIELD,
    account_id: str = Field(description="Account id."),
    symbol: str = Field(description="Ticker symbol."),
    side: str = Field(description="'buy' or 'sell'."),
    quantity: str = Field(description="Decimal quantity string."),
    mode: str = MODE_FIELD,
) -> mcp_models.ValidationOut:
    return await _run("validate_investment_action", {
        "api_key": api_key, "account_id": account_id, "symbol": symbol,
        "side": side, "quantity": quantity, "mode": mode})


@server.tool(structured_output=True, description=(
    "READ-ONLY (permission: read). Status of an order or a proposal "
    "approval (pass exactly one of order_id / approval_id). A pending "
    "proposal reports status='pending_authorization' with its DRAFT orders "
    "(simulated, never submitted until the human confirms)."
))
async def get_order_status(
    api_key: str = API_KEY_FIELD,
    order_id: str | None = Field(default=None, description="Order id."),
    approval_id: str | None = Field(default=None, description="Proposal approval id."),
    mode: str = MODE_FIELD,
) -> mcp_models.OrderStatusOut:
    return await _run("get_order_status", {
        "api_key": api_key, "order_id": order_id, "approval_id": approval_id,
        "mode": mode})


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
