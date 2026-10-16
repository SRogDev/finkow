"""Market data: keyless providers, caching, graceful degradation."""

from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from app.market import (
    CachedMarketData,
    CoinGeckoProvider,
    MarketDataUnavailable,
    StooqProvider,
    SymbolNotFound,
    YahooFinanceProvider,
)

STOOQ_CSV = (
    "Symbol,Date,Time,Open,High,Low,Close,Volume\r\n"
    "AAPL.US,2026-09-25,22:00:00,149.00,151.00,148.50,150.25,12345678\r\n"
)
COINGECKO_JSON = b'{"bitcoin":{"usd":67234.5,"last_updated_at":1758835200}}'


def make_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def ok_handler(request: httpx.Request) -> httpx.Response:
    if "stooq.com" in str(request.url):
        return httpx.Response(200, text=STOOQ_CSV)
    if "coingecko.com" in str(request.url):
        return httpx.Response(200, content=COINGECKO_JSON)
    return httpx.Response(404)


def test_stooq_parses_close_price():
    client = make_client(ok_handler)
    md = CachedMarketData(client=client)
    q = _run(md.get_quote("AAPL"))
    assert q.symbol == "AAPL"
    assert q.price == Decimal("150.25")
    assert q.provider == "stooq"
    assert q.stale is False


def test_coingecko_parses_btc_price():
    client = make_client(ok_handler)
    md = CachedMarketData(client=client)
    q = _run(md.get_quote("BTC"))
    assert q.symbol == "BTC"
    assert q.price == Decimal("67234.5")
    assert q.provider == "coingecko"


def test_cache_avoids_second_network_call():
    calls = {"n": 0}

    def counting(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return ok_handler(request)

    md = CachedMarketData(client=make_client(counting), ttl_seconds=60)
    _run(md.get_quote("AAPL"))
    _run(md.get_quote("AAPL"))
    assert calls["n"] == 1


def test_offline_serves_stale_cache():
    md = CachedMarketData(client=make_client(ok_handler), ttl_seconds=0)
    fresh = _run(md.get_quote("AAPL"))
    assert fresh.stale is False

    def down(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    md_down = CachedMarketData(client=make_client(down), ttl_seconds=0)
    md_down._cache["AAPL"] = (fresh, datetime.now(UTC))
    stale = _run(md_down.get_quote("AAPL"))
    assert stale.stale is True
    assert stale.price == fresh.price


def test_offline_without_cache_raises():
    def down(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    md = CachedMarketData(client=make_client(down))
    with pytest.raises(MarketDataUnavailable):
        _run(md.get_quote("AAPL"))


def test_unknown_symbol_raises_not_found():
    def na_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="Symbol,Date,Time,Open,High,Low,Close,Volume\r\nAAPL.US,N/A,N/A,N/A,N/A,N/A,N/A,N/A\r\n",
        )

    md = CachedMarketData(providers=[StooqProvider()], client=make_client(na_handler))
    with pytest.raises(SymbolNotFound):
        _run(md.get_quote("AAPL"))


def test_provider_routing():
    assert CoinGeckoProvider().supports("BTC")
    assert CoinGeckoProvider().supports("eth")
    assert not CoinGeckoProvider().supports("AAPL")
    assert StooqProvider().supports("AAPL")
    assert not StooqProvider().supports("BTC")
    assert YahooFinanceProvider().supports("AAPL")
    assert not YahooFinanceProvider().supports("BTC")


YAHOO_JSON = (
    b'{"chart":{"result":[{"meta":{"currency":"USD","symbol":"AAPL",'
    b'"regularMarketPrice":232.14}}],"error":null}}'
)


def test_yahoo_fallback_when_stooq_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        if "stooq.com" in str(request.url):
            raise httpx.ConnectError("blocked")
        if "yahoo.com" in str(request.url):
            return httpx.Response(200, content=YAHOO_JSON)
        return httpx.Response(404)

    md = CachedMarketData(client=make_client(handler))
    q = _run(md.get_quote("AAPL"))
    assert q.provider == "yahoo"
    assert q.price == Decimal("232.14")


def test_yahoo_unknown_symbol_raises_not_found():
    body = b'{"chart":{"result":null,"error":{"code":"Not Found"}}}'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    md = CachedMarketData(providers=[YahooFinanceProvider()], client=make_client(handler))
    with pytest.raises(SymbolNotFound):
        _run(md.get_quote("NOPEXYZ"))


def _run(coro):
    import asyncio

    return asyncio.run(coro)
