"""OpportunityRadar: market data + news -> ranked opportunities with reasoning.

For each watched symbol the radar gathers the live price, fundamentals, and a
recent headline (all through the ports — never hardcoded), then asks the LLM
port to rank them with plain-language reasoning. Unknown symbols are skipped;
an empty watchlist yields an empty list, never an invented one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.agents.events import EventLog
from app.market import SymbolNotFound
from app.ports import ChatMessage, LLMPort, MarketDataPort, ProviderError

TASK_MARKER = "[finkow-task: radar-rank]"

_SYSTEM_PROMPT = (
    TASK_MARKER
    + " You are Finkow's opportunity radar. Given one line per asset"
    + " (SYMBOL | PRICE | PE | NEWS), respond with a JSON object only: "
    + '{"opportunities": [{"symbol": "<TICKER>", "score": <0-100 number>, '
    + '"price": "<price as given>", "reasoning": "<2 plain sentences citing '
    + 'the actual price and P/E given, never invent numbers>"}]}. '
    + "Rank best-first. Plain language, zero jargon. This is paper money."
)


@dataclass(frozen=True)
class Opportunity:
    symbol: str
    score: float
    price: Decimal
    reasoning: str


class OpportunityRadar:
    """Scans a watchlist and returns ranked, reasoned opportunities."""

    def __init__(
        self,
        market: MarketDataPort,
        llm: LLMPort,
        events: EventLog | None = None,
    ) -> None:
        self._market = market
        self._llm = llm
        self._events = events or EventLog()

    async def scan(self, symbols: list[str]) -> list[Opportunity]:
        self._events.append("radar", "radar.scan_started", {"symbols": symbols})
        fact_lines: list[str] = []
        for raw in symbols:
            sym = raw.upper().strip()
            if not sym:
                continue
            try:
                quote = await self._market.get_quote(sym)
            except (SymbolNotFound, ProviderError):
                continue
            try:
                fundamentals = await self._market.get_fundamentals(sym)
            except ProviderError:
                fundamentals = None
            try:
                news = await self._market.get_news(sym, limit=1)
            except ProviderError:
                news = []
            pe = fundamentals.pe_ratio if fundamentals and fundamentals.pe_ratio else None
            headline = news[0].headline if news else "no recent headlines"
            fact_lines.append(
                f"SYMBOL: {sym} | PRICE: {quote.price} | "
                f"PE: {pe if pe is not None else 'none'} | NEWS: {headline}"
            )
        if not fact_lines:
            self._events.append("radar", "radar.completed", {"count": 0})
            return []
        try:
            raw = await self._llm.complete(
                [ChatMessage(role="user", content="\n".join(fact_lines))],
                system=_SYSTEM_PROMPT,
                json_mode=True,
            )
            opportunities = self._validate(json.loads(raw))
        except (ProviderError, json.JSONDecodeError) as exc:
            raise ValueError(f"radar could not rank opportunities: {exc}") from exc
        self._events.append(
            "radar",
            "radar.completed",
            {"count": len(opportunities), "symbols": [o.symbol for o in opportunities]},
        )
        return opportunities

    def _validate(self, data: dict) -> list[Opportunity]:
        out: list[Opportunity] = []
        try:
            items = data["opportunities"]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"radar JSON missing opportunities: {exc}") from exc
        for item in items:
            try:
                out.append(
                    Opportunity(
                        symbol=str(item["symbol"]).upper().strip(),
                        score=float(item["score"]),
                        price=Decimal(str(item["price"])),
                        reasoning=str(item["reasoning"]),
                    )
                )
            except (KeyError, TypeError, InvalidOperation, ValueError) as exc:
                raise ValueError(f"bad opportunity entry: {exc}") from exc
        out.sort(key=lambda o: o.score, reverse=True)
        return out
