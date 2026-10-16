"""v2 compatibility facade: opportunity scanning now lives in ``OpportunityHunter``.

The logic moved to :mod:`app.agents.hunter` (not duplicated). This module
re-exports the v2 names and keeps the exact v2 event stream
("radar"/"radar.scan_started"/"radar.completed") so existing callers and
tests keep working unchanged.
"""

from __future__ import annotations

from app.agents.events import EventLog
from app.agents.hunter import Opportunity, OpportunityHunter
from app.ports import LLMPort, MarketDataPort

__all__ = ["Opportunity", "OpportunityHunter", "OpportunityRadar"]


class OpportunityRadar:
    """Thin facade over :class:`OpportunityHunter` preserving the v2 contract."""

    def __init__(
        self,
        market: MarketDataPort,
        llm: LLMPort,
        events: EventLog | None = None,
    ) -> None:
        self._agent = OpportunityHunter(market, llm, events, agent_name="radar")

    async def scan(self, symbols: list[str]) -> list[Opportunity]:
        return await self._agent.scan(symbols)
