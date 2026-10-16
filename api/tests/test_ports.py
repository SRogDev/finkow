"""Provider ports: mocks, AIsa adapters, direct fallback, TTL cache.

RED phase: these tests pin the v2 provider contract before implementation.
"""

import asyncio
import json
from decimal import Decimal

import httpx
import pytest

from app.market import MarketDataUnavailable, Quote, SymbolNotFound


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- contracts


def test_port_protocols_importable():
    from app import ports

    assert hasattr(ports, "MarketDataPort")
    assert hasattr(ports, "LLMPort")
    assert hasattr(ports, "WebSearchPort")


def test_mock_market_data_quotes_are_deterministic():
    from app.providers.mock import MockMarketData

    md = MockMarketData()
    q1 = _run(md.get_quote("AAPL"))
    q2 = _run(md.get_quote("aapl"))
    assert q1.price == q2.price == Decimal("150.00")
    assert q1.provider == "mock"
    assert isinstance(q1, Quote)


def test_mock_market_data_unknown_symbol():
    from app.providers.mock import MockMarketData

    with pytest.raises(SymbolNotFound):
        _run(MockMarketData().get_quote("NOPEXYZ"))


def test_mock_fundamentals_and_news():
    from app.providers.mock import MockMarketData

    md = MockMarketData()
    f = _run(md.get_fundamentals("AAPL"))
    assert f is not None
    assert f.symbol == "AAPL"
    assert "Apple" in f.name
    assert f.pe_ratio == Decimal("28.5")
    news = _run(md.get_news("AAPL", limit=2))
    assert 1 <= len(news) <= 2
    assert all(n.symbol == "AAPL" and n.headline for n in news)


def test_mock_llm_plan_is_valid_for_each_risk_level():
    from app.ports import ChatMessage
    from app.providers.mock import MockLLM

    llm = MockLLM()
    for risk in ("low", "medium", "high"):
        raw = _run(
            llm.complete(
                [ChatMessage(role="user", content=f"RISK: {risk}\nAMOUNT: 1000\nHORIZON: 5")],
                system="[finkow-task: goal-plan] Make a plan.",
                json_mode=True,
            )
        )
        plan = json.loads(raw)
        weights = [Decimal(str(a["weight"])) for a in plan["allocations"]]
        assert abs(sum(weights) - Decimal("1")) < Decimal("0.001"), risk
        assert len(plan["allocations"]) >= 2
        assert plan["summary_plain"]
        assert "1000" in plan["summary_plain"]


def test_mock_llm_radar_ranking_has_reasoning_with_numbers():
    from app.ports import ChatMessage
    from app.providers.mock import MockLLM

    llm = MockLLM()
    facts = (
        "SYMBOL: AAPL | PRICE: 150.00 | PE: 28.5 | NEWS: Apple unveils new chip\n"
        "SYMBOL: NVDA | PRICE: 130.00 | PE: 45.2 | NEWS: Data-center demand surges\n"
        "SYMBOL: BND | PRICE: 75.00 | PE: none | NEWS: Bonds steady\n"
    )
    raw = _run(
        llm.complete(
            [ChatMessage(role="user", content=facts)],
            system="[finkow-task: radar-rank] Rank opportunities.",
            json_mode=True,
        )
    )
    opps = json.loads(raw)["opportunities"]
    assert len(opps) >= 3
    for o in opps:
        assert o["symbol"] and o["reasoning"] and o["score"] is not None
    # reasoning must cite real numbers from the facts, not invented ones
    blob = json.dumps(opps)
    assert "150.00" in blob and "28.5" in blob


def test_mock_search_returns_results():
    from app.providers.mock import MockWebSearch

    results = _run(MockWebSearch().search("AAPL stock news", max_results=3))
    assert 1 <= len(results) <= 3
    assert all(r.title and r.url for r in results)


# ---------------------------------------------------------------- direct + cache + fallback


def _v1_client_ok():
    header = "Symbol,Date,Time,Open,High,Low,Close,Volume\r\n"
    row = "AAPL.US,2026-09-25,22:00:00,149,151,148.5,150.25,1\r\n"
    csv = header + row

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=csv)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_direct_adapter_delegates_quotes_to_v1_providers():
    from app.market import CachedMarketData
    from app.providers.direct import DirectQuoteAdapter

    inner = CachedMarketData(client=_v1_client_ok())
    adapter = DirectQuoteAdapter(inner)
    q = _run(adapter.get_quote("AAPL"))
    assert q.price == Decimal("150.25")
    assert q.provider == "stooq"
    assert _run(adapter.get_fundamentals("AAPL")) is None
    assert _run(adapter.get_news("AAPL")) == []


def test_cached_port_respects_ttl():
    from app.providers.cached import CachedMarketDataPort
    from app.providers.mock import MockMarketData

    calls = {"n": 0}
    inner = MockMarketData()

    orig = inner.get_quote

    async def counting(symbol):
        calls["n"] += 1
        return await orig(symbol)

    inner.get_quote = counting  # type: ignore[method-assign]
    port = CachedMarketDataPort(inner, ttl_seconds=3600)
    _run(port.get_quote("AAPL"))
    _run(port.get_quote("AAPL"))
    assert calls["n"] == 1
    expired = CachedMarketDataPort(inner, ttl_seconds=0)
    _run(expired.get_quote("AAPL"))
    _run(expired.get_quote("AAPL"))
    assert calls["n"] == 3


def test_fallback_uses_secondary_when_primary_fails():
    from app.market import CachedMarketData
    from app.providers.cached import FallbackMarketData
    from app.providers.direct import DirectQuoteAdapter
    from app.providers.mock import MockMarketData

    class Broken:
        name = "broken"

        async def get_quote(self, symbol):
            raise MarketDataUnavailable("down")

        async def get_fundamentals(self, symbol):
            return None

        async def get_news(self, symbol, limit=5):
            return []

    fb = FallbackMarketData(Broken(), DirectQuoteAdapter(CachedMarketData(client=_v1_client_ok())))
    q = _run(fb.get_quote("AAPL"))
    assert q.price == Decimal("150.25")

    # primary working means fallback never touched
    fb2 = FallbackMarketData(MockMarketData(), Broken())
    assert _run(fb2.get_quote("BTC")).price == Decimal("60000.00")


# ---------------------------------------------------------------- AIsa adapters


def _aisa_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


AISA_BARS = {
    "data": [
        {"date": "2026-10-01", "close": 149.0},
        {"date": "2026-10-02", "close": 150.25},
    ]
}


def test_aisa_market_data_request_shape_and_parsing():
    from app.providers.aisa import AisaMarketData

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        assert request.url.path == "/apis/v1/financial/prices"
        params = dict(request.url.params)
        assert params["ticker"] == "AAPL"
        assert params["interval"] == "day"
        return httpx.Response(200, json=AISA_BARS)

    md = AisaMarketData(api_key="k-test", client=_aisa_client(handler))
    q = _run(md.get_quote("AAPL"))
    assert q.price == Decimal("150.25")  # last bar's close
    assert q.provider == "aisa"
    assert seen["auth"] == "Bearer k-test"


def test_aisa_market_data_unexpected_shape_raises_provider_error():
    from app.ports import ProviderError
    from app.providers.aisa import AisaMarketData

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"weird": True})

    md = AisaMarketData(api_key="k", client=_aisa_client(handler))
    with pytest.raises(ProviderError):
        _run(md.get_quote("AAPL"))


def test_aisa_llm_request_shape():
    from app.ports import ChatMessage
    from app.providers.aisa import AisaLLM

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        body = json.loads(request.content.decode())
        assert body["model"] == "gpt-4o-mini"
        assert body["messages"][0]["role"] == "system"
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})

    llm = AisaLLM(api_key="k-test", client=_aisa_client(handler), model="gpt-4o-mini")
    out = _run(llm.complete([ChatMessage(role="user", content="hi")], system="sys"))
    assert out == "hello"
    assert seen["url"] == "https://api.aisa.one/v1/chat/completions"
    assert seen["auth"] == "Bearer k-test"


def test_aisa_web_search_request_shape():
    from app.providers.aisa import AisaWebSearch

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        body = json.loads(request.content.decode())
        assert body["query"] == "AAPL news"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "t", "url": "https://x.example/1", "content": "snippet here"}
                ]
            },
        )

    s = AisaWebSearch(api_key="k", client=_aisa_client(handler))
    results = _run(s.search("AAPL news", max_results=3))
    assert len(results) == 1
    assert results[0].snippet == "snippet here"
    assert "tavily" in seen["path"]


# ---------------------------------------------------------------- builders


def test_builders_choose_mock_without_key(monkeypatch):
    from app.providers import build_llm, build_market_port, build_search

    monkeypatch.delenv("AISA_API_KEY", raising=False)
    assert build_llm().name == "mock"
    assert build_search().name == "mock"
    port = build_market_port()
    assert _run(port.get_quote("AAPL")).provider == "mock"


def test_builders_choose_aisa_with_key(monkeypatch):
    from app.providers import build_llm, build_market_port, build_search

    monkeypatch.setenv("AISA_API_KEY", "k-test")
    assert build_llm().name == "aisa"
    assert build_search().name == "aisa"
    assert "aisa" in build_market_port().name
