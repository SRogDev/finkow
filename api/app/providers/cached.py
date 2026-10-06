"""Quote caching and provider fallback for the MarketDataPort.

- ``CachedMarketDataPort``: TTL cache in front of any port. Quotes are the hot
  path — cache them aggressively regardless of provider (cost + latency).
- ``FallbackMarketData``: try primary, fall back to secondary on any
  ``MarketDataError`` (provider down, bad shape, unknown symbol there).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from app.market import MarketDataError, Quote
from app.ports import Fundamentals, MarketDataPort, NewsItem


def _default_ttl() -> int:
    try:
        return max(int(os.environ.get("FINKOW_QUOTE_TTL_SECONDS", "60")), 0)
    except ValueError:
        return 60


class CachedMarketDataPort:
    """TTL-cached quotes; fundamentals/news pass through uncached."""

    def __init__(self, inner: MarketDataPort, ttl_seconds: int | None = None) -> None:
        self._inner = inner
        self._ttl = timedelta(
            seconds=ttl_seconds if ttl_seconds is not None else _default_ttl()
        )
        self._cache: dict[str, tuple[Quote, datetime]] = {}

    @property
    def name(self) -> str:
        return f"cached({self._inner.name})"

    async def get_quote(self, symbol: str) -> Quote:
        sym = symbol.upper().strip()
        now = datetime.now(UTC)
        cached = self._cache.get(sym)
        if cached and now - cached[1] < self._ttl:
            return cached[0]
        quote = await self._inner.get_quote(sym)
        self._cache[sym] = (quote, now)
        return quote

    async def get_fundamentals(self, symbol: str) -> Fundamentals | None:
        return await self._inner.get_fundamentals(symbol)

    async def get_news(self, symbol: str, limit: int = 5) -> list[NewsItem]:
        return await self._inner.get_news(symbol, limit)


class FallbackMarketData:
    """Primary port with a secondary for quotes when the primary errors."""

    def __init__(self, primary: MarketDataPort, secondary: MarketDataPort) -> None:
        self._primary = primary
        self._secondary = secondary

    @property
    def name(self) -> str:
        return f"fallback({self._primary.name},{self._secondary.name})"

    async def get_quote(self, symbol: str) -> Quote:
        try:
            return await self._primary.get_quote(symbol)
        except MarketDataError:
            return await self._secondary.get_quote(symbol)

    async def get_fundamentals(self, symbol: str) -> Fundamentals | None:
        try:
            result = await self._primary.get_fundamentals(symbol)
        except MarketDataError:
            result = None
        if result is None:
            try:
                return await self._secondary.get_fundamentals(symbol)
            except MarketDataError:
                return None
        return result

    async def get_news(self, symbol: str, limit: int = 5) -> list[NewsItem]:
        try:
            return await self._primary.get_news(symbol, limit)
        except MarketDataError:
            return await self._secondary.get_news(symbol, limit)
