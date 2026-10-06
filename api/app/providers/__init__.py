"""Provider wiring: pick implementations from the environment.

- ``AISA_API_KEY`` set → AIsa adapters (market data with free direct fallback,
  OpenAI-compatible LLM, Tavily web search).
- Absent → deterministic mocks (market data falls back to the free direct
  chain for symbols outside the mock universe).

Everything is wrapped in the TTL quote cache.
"""

from __future__ import annotations

import os

from app.ports import LLMPort, MarketDataPort, WebSearchPort
from app.providers.aisa import AisaLLM, AisaMarketData, AisaWebSearch
from app.providers.cached import CachedMarketDataPort, FallbackMarketData
from app.providers.direct import DirectQuoteAdapter
from app.providers.mock import MockLLM, MockMarketData, MockWebSearch


def _aisa_key() -> str | None:
    return os.environ.get("AISA_API_KEY") or None


def build_market_port() -> MarketDataPort:
    key = _aisa_key()
    if key:
        primary: MarketDataPort = AisaMarketData(key)
    else:
        primary = MockMarketData()
    chained: MarketDataPort = FallbackMarketData(primary, DirectQuoteAdapter())
    return CachedMarketDataPort(chained)


def build_llm() -> LLMPort:
    key = _aisa_key()
    if key:
        return AisaLLM(key)
    return MockLLM()


def build_search() -> WebSearchPort:
    key = _aisa_key()
    if key:
        return AisaWebSearch(key)
    return MockWebSearch()
