"""Deterministic mock providers: clearly-labeled fake data for tests and demos.

Used automatically when ``AISA_API_KEY`` is absent. Every value here is
hardcoded *mock* data — that is the point of a test double. Production agents
must still read all market facts through the port; they never hardcode prices.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from decimal import Decimal

from app.market import Quote, SymbolNotFound
from app.ports import ChatMessage, Fundamentals, NewsItem, SearchResult

# symbol -> (price, name, sector, pe_ratio|None, market_cap_usd|None)
_MOCK_UNIVERSE: dict[str, tuple[str, str, str, str | None, str | None]] = {
    "AAPL": ("150.00", "Apple Inc.", "Technology", "28.5", "3000000000000"),
    "MSFT": ("420.00", "Microsoft Corp.", "Technology", "32.1", "3100000000000"),
    "NVDA": ("130.00", "NVIDIA Corp.", "Semiconductors", "45.2", "3200000000000"),
    "VTI": ("280.00", "Vanguard Total Stock Market ETF", "ETF", None, None),
    "BND": ("75.00", "Vanguard Total Bond Market ETF", "ETF", None, None),
    "BTC": ("60000.00", "Bitcoin", "Crypto", None, "1200000000000"),
    "ETH": ("3000.00", "Ethereum", "Crypto", None, "360000000000"),
    "SOL": ("150.00", "Solana", "Crypto", None, "70000000000"),
}

_MOCK_NEWS: dict[str, list[tuple[str, str]]] = {
    "AAPL": [
        ("Apple unveils new chip lineup for 2026 devices", "MockWire"),
        ("Analysts raise Apple price targets on services growth", "MockWire"),
    ],
    "MSFT": [("Microsoft expands AI cloud capacity", "MockWire")],
    "NVDA": [("Data-center demand surges for AI accelerators", "MockWire")],
    "VTI": [("Broad market index steady amid mixed earnings", "MockWire")],
    "BND": [("Bonds steady as rate expectations hold", "MockWire")],
    "BTC": [("Bitcoin holds above key level on ETF inflows", "MockWire")],
    "ETH": [("Ethereum upgrade boosts network activity", "MockWire")],
    "SOL": [("Solana throughput hits new record", "MockWire")],
}

# risk level -> [(symbol, weight, rationale)]
_PLAN_TABLES: dict[str, list[tuple[str, str, str]]] = {
    "low": [
        ("BND", "0.50", "Bonds cushion the ride when markets wobble."),
        ("VTI", "0.30", "Owns a slice of the whole stock market in one go."),
        ("AAPL", "0.10", "A steady earner with strong cash flow."),
        ("MSFT", "0.10", "Diversifies across software and cloud."),
    ],
    "medium": [
        ("VTI", "0.45", "Broad market growth as the core."),
        ("AAPL", "0.20", "Quality large-cap earnings compounder."),
        ("MSFT", "0.15", "Cloud and AI exposure."),
        ("BND", "0.10", "A stabilizer for drawdowns."),
        ("BTC", "0.10", "A small high-growth diversifier."),
    ],
    "high": [
        ("NVDA", "0.30", "AI infrastructure growth leader."),
        ("BTC", "0.25", "High-volatility digital asset."),
        ("SOL", "0.15", "Fast-growing crypto network."),
        ("AAPL", "0.15", "Ballast from a profitable giant."),
        ("VTI", "0.15", "Keeps one foot in the broad market."),
    ],
}


class MockMarketData:
    """Deterministic quotes/fundamentals/news. Provider name is ``mock``."""

    name = "mock"

    def __init__(self) -> None:
        # Mutable copy so tests can simulate market movement.
        self._prices: dict[str, Decimal] = {
            sym: Decimal(row[0]) for sym, row in _MOCK_UNIVERSE.items()
        }

    def set_price(self, symbol: str, price: Decimal) -> None:
        """Test/demo hook: move a mock price to simulate the market."""
        sym = symbol.upper().strip()
        if sym not in _MOCK_UNIVERSE:
            raise SymbolNotFound(sym)
        self._prices[sym] = price

    async def get_quote(self, symbol: str) -> Quote:
        sym = symbol.upper().strip()
        row = _MOCK_UNIVERSE.get(sym)
        if row is None:
            raise SymbolNotFound(sym)
        return Quote(
            symbol=sym,
            price=self._prices[sym],
            currency="USD",
            as_of=datetime.now(UTC),
            provider=self.name,
        )

    async def get_fundamentals(self, symbol: str) -> Fundamentals | None:
        sym = symbol.upper().strip()
        row = _MOCK_UNIVERSE.get(sym)
        if row is None:
            raise SymbolNotFound(sym)
        _, name, sector, pe, cap = row
        return Fundamentals(
            symbol=sym,
            name=name,
            sector=sector,
            pe_ratio=Decimal(pe) if pe else None,
            market_cap_usd=Decimal(cap) if cap else None,
        )

    async def get_news(self, symbol: str, limit: int = 5) -> list[NewsItem]:
        sym = symbol.upper().strip()
        if sym not in _MOCK_UNIVERSE:
            raise SymbolNotFound(sym)
        return [
            NewsItem(symbol=sym, headline=h, source=s)
            for h, s in _MOCK_NEWS.get(sym, [])[: max(limit, 0)]
        ]


def _first_group(pattern: str, text: str, default: str) -> str:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else default


class MockLLM:
    """Deterministic canned completions keyed by ``[finkow-task: ...]`` markers.

    The agents embed real facts (from the ports) in the prompt; the mock only
    shapes them into the expected JSON/text envelope. Provider name ``mock``.
    """

    name = "mock"

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        system: str = "",
        json_mode: bool = False,
    ) -> str:
        user_text = "\n".join(m.content for m in messages if m.role == "user")
        if "[finkow-task: goal-plan]" in system:
            return self._plan(user_text)
        if "[finkow-task: radar-rank]" in system:
            return self._rank(user_text)
        facts = user_text[:800]
        return f"In plain language (mock): {facts}"

    def _plan(self, user_text: str) -> str:
        risk = _first_group(r"RISK:\s*(\w+)", user_text, "medium").lower()
        amount = _first_group(r"AMOUNT:\s*([\d.,]+)", user_text, "1000")
        horizon = _first_group(r"HORIZON:\s*([\d.]+)", user_text, "5")
        table = _PLAN_TABLES.get(risk, _PLAN_TABLES["medium"])
        risk_word = {"low": "calm", "medium": "balanced", "high": "bold"}.get(risk, "balanced")
        plan = {
            "summary_plain": (
                f"A {risk_word} plan to grow ${amount} over {horizon} years: "
                f"spread across {len(table)} holdings so no single bet decides "
                f"the outcome. This is paper money — nothing here is financial advice."
            ),
            "horizon_years": float(horizon),
            "risk_level": risk,
            "allocations": [
                {"symbol": sym, "weight": weight, "rationale": rationale}
                for sym, weight, rationale in table
            ],
        }
        return json.dumps(plan)

    def _rank(self, user_text: str) -> str:
        opps: list[dict] = []
        for line in user_text.splitlines():
            m = re.match(
                r"SYMBOL:\s*(\w+)\s*\|\s*PRICE:\s*([\d.]+)\s*\|\s*PE:\s*([\d.]+|none)\s*\|\s*NEWS:\s*(.*)",
                line.strip(),
                re.IGNORECASE,
            )
            if not m:
                continue
            sym, price, pe_raw, headline = m.groups()
            pe = None if pe_raw.lower() == "none" else float(pe_raw)
            score = round(100.0 / pe, 2) if pe else 2.0
            pe_txt = pe_raw if pe else "n/a"
            if pe and pe < 35:
                verdict = "Valuation looks reasonable versus earnings."
            elif pe:
                verdict = "Priced for growth — higher risk, higher potential."
            else:
                verdict = "No earnings multiple available — steadier profile."
            opps.append(
                {
                    "symbol": sym,
                    "score": score,
                    "price": price,
                    "reasoning": (
                        f"{sym} trades at ${price} (P/E {pe_txt}). Headline: "
                        f"{headline}. {verdict}"
                    ),
                }
            )
        opps.sort(key=lambda o: o["score"], reverse=True)
        return json.dumps({"opportunities": opps})


class MockWebSearch:
    """Canned search results. Provider name ``mock``."""

    name = "mock"

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        q = query.lower()
        results = []
        for sym in _MOCK_UNIVERSE:
            if sym.lower() in q:
                for headline, source in _MOCK_NEWS.get(sym, [])[:2]:
                    results.append(
                        SearchResult(
                            title=headline,
                            url=f"https://mock.example/news/{sym.lower()}",
                            snippet=f"{headline} — via {source} (mock).",
                            source=source,
                        )
                    )
        if not results:
            results.append(
                SearchResult(
                    title=f"Mock results for: {query}",
                    url="https://mock.example/search",
                    snippet="No specific mock coverage; this is a placeholder result.",
                    source="MockWire",
                )
            )
        return results[: max(max_results, 1)]
