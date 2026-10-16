"""Market-data provider abstraction.

Keyless providers first (Stooq for stocks/ETFs, CoinGecko for crypto) behind a
common interface. Responses are cached (TTL); when providers are unreachable we
serve the last-known quote marked stale, and only raise when we have nothing.
"""

from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol

import httpx


class MarketDataError(Exception):
    """Base for all market-data failures."""


class SymbolNotFound(MarketDataError):
    """No provider knows this symbol."""


class MarketDataUnavailable(MarketDataError):
    """Providers unreachable and no cached quote to fall back to."""


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: Decimal
    currency: str = "USD"
    as_of: datetime = field(default_factory=lambda: datetime.now(UTC))
    provider: str = ""
    stale: bool = False


class MarketDataProvider(Protocol):
    name: str

    def supports(self, symbol: str) -> bool: ...

    async def fetch(self, client: httpx.AsyncClient, symbol: str) -> Quote: ...


# CoinGecko coin ids for the symbols we support in the MVP sandbox.
CRYPTO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "DOGE": "dogecoin",
    "XRP": "ripple",
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "LINK": "chainlink",
    "DOT": "polkadot",
}


class CoinGeckoProvider:
    """Keyless crypto prices. Rate-limited on the free tier — hence the cache."""

    name = "coingecko"

    def supports(self, symbol: str) -> bool:
        return symbol.upper() in CRYPTO_IDS

    async def fetch(self, client: httpx.AsyncClient, symbol: str) -> Quote:
        sym = symbol.upper()
        coin_id = CRYPTO_IDS[sym]
        url = (
            "https://api.coingecko.com/api/v3/simple/price"
            f"?ids={coin_id}&vs_currencies=usd&include_last_updated_at=true"
        )
        try:
            resp = await client.get(url, timeout=10.0)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataUnavailable(f"coingecko unreachable: {exc}") from exc
        data = resp.json().get(coin_id) or {}
        if "usd" not in data:
            raise SymbolNotFound(sym)
        ts = data.get("last_updated_at")
        as_of = datetime.fromtimestamp(ts, tz=UTC) if ts else datetime.now(UTC)
        return Quote(symbol=sym, price=Decimal(str(data["usd"])), as_of=as_of, provider=self.name)


class StooqProvider:
    """Keyless stock/ETF quotes via Stooq's free CSV endpoint."""

    name = "stooq"

    def supports(self, symbol: str) -> bool:
        return symbol.upper() not in CRYPTO_IDS

    async def fetch(self, client: httpx.AsyncClient, symbol: str) -> Quote:
        sym = symbol.upper()
        # "AAPL" -> "aapl.us"; explicit "AAPL.US"/"AAPL.XETRA" style passes through.
        stooq_sym = sym.lower() if "." in sym else f"{sym.lower()}.us"
        url = f"https://stooq.com/q/l/?s={stooq_sym}&f=sd2t2ohlcv&h&e=csv"
        try:
            resp = await client.get(url, timeout=10.0)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataUnavailable(f"stooq unreachable: {exc}") from exc
        rows = list(csv.DictReader(io.StringIO(resp.text)))
        if not rows:
            raise SymbolNotFound(sym)
        close = (rows[0].get("Close") or "").strip()
        if not close or close.upper() == "N/A":
            raise SymbolNotFound(sym)
        return Quote(symbol=sym.split(".")[0], price=Decimal(close), provider=self.name)


class YahooFinanceProvider:
    """Fallback stock/ETF quotes via Yahoo's keyless chart API.

    Used when Stooq is unreachable. No API key; needs a browser-like UA.
    """

    name = "yahoo"

    def supports(self, symbol: str) -> bool:
        return symbol.upper() not in CRYPTO_IDS

    async def fetch(self, client: httpx.AsyncClient, symbol: str) -> Quote:
        sym = symbol.upper().split(".")[0]
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d"
        try:
            resp = await client.get(
                url,
                timeout=10.0,
                headers={"User-Agent": "Mozilla/5.0 (compatible; finkow/0.1)"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise MarketDataUnavailable(f"yahoo unreachable: {exc}") from exc
        try:
            meta = resp.json()["chart"]["result"][0]["meta"]
            price = meta["regularMarketPrice"]
        except (KeyError, IndexError, TypeError) as exc:
            raise SymbolNotFound(sym) from exc
        if price is None:
            raise SymbolNotFound(sym)
        return Quote(symbol=sym, price=Decimal(str(price)), provider=self.name)


def build_client() -> httpx.AsyncClient:
    """HTTP client for market-data calls.

    The proxy/CA come from the environment explicitly (not trust_env): some
    runtimes ship no_proxy entries (bracketed IPv6 hosts) that httpx cannot
    parse, which would crash client construction. Market-data calls are always
    external, so no_proxy bypass is irrelevant here.
    """
    proxy = (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
    )
    verify = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE") or True
    return httpx.AsyncClient(
        headers={"User-Agent": "finkow/0.1"},
        trust_env=False,
        proxy=proxy,
        verify=verify,
    )


class CachedMarketData:
    """Tries providers in order; caches fresh quotes; degrades to stale cache."""

    def __init__(
        self,
        providers: list[MarketDataProvider] | None = None,
        ttl_seconds: int = 60,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.providers = providers or [
            CoinGeckoProvider(),
            StooqProvider(),
            YahooFinanceProvider(),  # fallback when Stooq is unreachable
        ]
        self.ttl = timedelta(seconds=ttl_seconds)
        self._client = client or build_client()
        self._cache: dict[str, tuple[Quote, datetime]] = {}

    async def get_quote(self, symbol: str) -> Quote:
        sym = symbol.upper().strip()
        if not sym:
            raise SymbolNotFound(symbol)
        now = datetime.now(UTC)
        cached = self._cache.get(sym)
        if cached and now - cached[1] < self.ttl:
            return cached[0]

        last_error: MarketDataError | None = None
        for provider in self.providers:
            if not provider.supports(sym):
                continue
            try:
                quote = await provider.fetch(self._client, sym)
            except SymbolNotFound:
                continue
            except MarketDataUnavailable as exc:
                last_error = exc
                continue
            self._cache[sym] = (quote, now)
            return quote

        # Graceful degradation: serve last-known price marked stale.
        if cached:
            return replace(cached[0], stale=True)
        if last_error is not None:
            raise last_error
        raise SymbolNotFound(sym)
