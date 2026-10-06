"""Free keyless quote fallback: wraps the v1 CachedMarketData engine.

Used when AIsa is unavailable (or failing) so quotes keep flowing at zero
cost. Fundamentals/news are not available on the free path — callers get
``None`` / ``[]`` instead of invented data.
"""

from __future__ import annotations

from app.market import CachedMarketData, Quote
from app.ports import Fundamentals, NewsItem


class DirectQuoteAdapter:
    """MarketDataPort over the v1 provider chain (CoinGecko/Stooq/Yahoo)."""

    name = "direct"

    def __init__(self, inner: CachedMarketData | None = None) -> None:
        self._inner = inner or CachedMarketData()

    async def get_quote(self, symbol: str) -> Quote:
        return await self._inner.get_quote(symbol)

    async def get_fundamentals(self, symbol: str) -> Fundamentals | None:
        return None

    async def get_news(self, symbol: str, limit: int = 5) -> list[NewsItem]:
        return []
