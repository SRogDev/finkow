"""FinancialAnalyst: fundamentals, valuation sanity, and risk analysis.

New in v2.1 (Roger's 4-agent harness). For a symbol it gathers price,
fundamentals, and recent headlines through the ports, then produces a
structured verdict with deterministic rules:

- P/E < 0 ............ "risky"   (negative earnings)
- P/E > 50 ........... "watch"   (richly valued)
- P/E missing ........ "neutral" (ETF / crypto: no earnings multiple)
- otherwise .......... "healthy"

Risk flags are deterministic (valuation, asset-class volatility, missing
data). The LLM port only renders the plain-language summary — the verdict
never depends on it. Nothing here is financial advice and nothing promises
returns; the output verifier rejects guaranteed-returns language.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.agents.events import EventLog
from app.governance.metering import CreditsExhausted
from app.market import SymbolNotFound
from app.ports import ChatMessage, LLMPort, MarketDataPort, ProviderError

TASK_MARKER = "[finkow-task: analyze]"

_SYSTEM_PROMPT = (
    f"{TASK_MARKER} You summarize a structured stock analysis in plain "
    "language. Use ONLY the numbers in ANALYSIS. 2-3 short sentences, zero "
    "jargon, no buy/sell recommendation, no guaranteed outcomes. This is "
    "paper money."
)


@dataclass(frozen=True)
class Analysis:
    symbol: str
    price: Decimal
    pe_ratio: Decimal | None
    verdict: str  # "healthy" | "watch" | "risky" | "neutral"
    risk_flags: list[str] = field(default_factory=list)
    summary_plain: str = ""


class FinancialAnalyst:
    """Fundamentals + valuation sanity + risk, in plain language."""

    def __init__(
        self,
        market: MarketDataPort,
        llm: LLMPort,
        events: EventLog | None = None,
        agent_name: str = "analyst",
    ) -> None:
        self._market = market
        self._llm = llm
        self._events = events or EventLog()
        self._agent_name = agent_name

    async def analyze(self, symbol: str) -> Analysis:
        sym = symbol.upper().strip()
        if not sym:
            raise ValueError("symbol is required")
        try:
            quote = await self._market.get_quote(sym)
        except CreditsExhausted:
            raise
        except (SymbolNotFound, ProviderError) as exc:
            raise ValueError(f"unknown symbol: {sym}") from exc
        try:
            fundamentals = await self._market.get_fundamentals(sym)
        except CreditsExhausted:
            raise
        except ProviderError:
            fundamentals = None
        try:
            news = await self._market.get_news(sym, limit=3)
        except CreditsExhausted:
            raise
        except ProviderError:
            news = []

        pe = fundamentals.pe_ratio if fundamentals else None
        sector = fundamentals.sector if fundamentals else "unknown"
        verdict, risk_flags = self._assess(sym, pe, sector, news)
        summary = await self._summarize(sym, quote.price, pe, verdict, risk_flags)
        analysis = Analysis(
            symbol=sym,
            price=quote.price,
            pe_ratio=pe,
            verdict=verdict,
            risk_flags=risk_flags,
            summary_plain=summary,
        )
        self._events.append(
            self._agent_name,
            f"{self._agent_name}.completed",
            {"symbol": sym, "verdict": verdict},
        )
        return analysis

    def _assess(
        self, symbol: str, pe: Decimal | None, sector: str, news: list
    ) -> tuple[str, list[str]]:
        flags: list[str] = []
        if pe is None:
            verdict = "neutral"
            flags.append("no earnings multiple available (ETF or crypto)")
        elif pe < 0:
            verdict = "risky"
            flags.append("negative earnings")
        elif pe > 50:
            verdict = "watch"
            flags.append("rich valuation: high P/E multiple")
        elif pe > 40:
            verdict = "watch"
            flags.append("elevated valuation: above-average P/E")
        else:
            verdict = "healthy"
        if sector.lower() == "crypto":
            flags.append("high-volatility asset class")
        if not news:
            flags.append("no recent headlines found")
        return verdict, flags

    async def _summarize(
        self,
        symbol: str,
        price: Decimal,
        pe: Decimal | None,
        verdict: str,
        risk_flags: list[str],
    ) -> str:
        facts = (
            f"SYMBOL: {symbol} | PRICE: {price} | "
            f"PE: {pe if pe is not None else 'none'} | VERDICT: {verdict} | "
            f"RISKS: {'; '.join(risk_flags) if risk_flags else 'none noted'}"
        )
        try:
            return await self._llm.complete(
                [ChatMessage(role="user", content=facts)],
                system=_SYSTEM_PROMPT,
            )
        except CreditsExhausted:
            raise
        except ProviderError:
            pe_word = f"P/E {pe}" if pe is not None else "no P/E available"
            return (
                f"{symbol} at ${price} ({pe_word}): {verdict}. "
                + (
                    "Watch out for: " + "; ".join(risk_flags) + "."
                    if risk_flags
                    else "No major risk flags."
                )
                + " This is paper money — not financial advice."
            )
