"""v2 compatibility facade: paper execution now lives in ``InvestmentExecutor``.

The logic moved to :mod:`app.agents.executor` (not duplicated). This module
re-exports the v2 names and keeps the exact v2 event stream
("pilot"/"pilot.invest_started"/"pilot.invest_completed"/"pilot.trade_executed")
so existing callers and tests keep working unchanged.
"""

from __future__ import annotations

from decimal import Decimal

from app.agents.events import EventLog
from app.agents.executor import (
    InvestmentExecutor,
    InvestResult,
    TradeRecord,
)
from app.agents.planner import Allocation
from app.governance.audit import AuditLog
from app.ports import MarketDataPort
from app.store import InMemoryStore

__all__ = ["InvestResult", "InvestmentExecutor", "PortfolioPilot", "TradeRecord"]


class PortfolioPilot:
    """Thin facade over :class:`InvestmentExecutor` preserving the v2 contract."""

    def __init__(
        self,
        store: InMemoryStore,
        market: MarketDataPort,
        events: EventLog | None = None,
    ) -> None:
        # Legacy v2 contract: no trade limits (exact v2 behavior preserved).
        # New callers should use InvestmentExecutor directly (safe defaults).
        self._agent = InvestmentExecutor(
            store,
            market,
            events,
            AuditLog(),
            agent_name="pilot",
            max_trade_usd=Decimal("999999999"),
            max_daily_trades=10**9,
        )

    async def invest(
        self, account_id: str, allocations: list[Allocation]
    ) -> InvestResult:
        return await self._agent.invest_paper(account_id, allocations)
