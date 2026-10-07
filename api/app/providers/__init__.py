"""Provider wiring: pick implementations from the environment.

- ``AISA_API_KEY`` set → AIsa adapters (market data with free direct fallback,
  OpenAI-compatible LLM, Tavily web search). Paid AIsa ports are wrapped in
  ``MeteredPort``: agents spend per-account credits on every paid call, with
  balance + daily/monthly caps enforced BEFORE the call (inside the cache and
  the fallback chain, so cached quotes and free fallbacks are never billed).
- Absent → deterministic mocks (market data falls back to the free direct
  chain for symbols outside the mock universe).

Everything is wrapped in the TTL quote cache.
"""

from __future__ import annotations

import os

from app.billing.credits import get_ledger
from app.governance.metering import MeteredPort, get_governor
from app.ports import LLMPort, MarketDataPort, WebSearchPort
from app.providers.aisa import AisaLLM, AisaMarketData, AisaWebSearch
from app.providers.cached import CachedMarketDataPort, FallbackMarketData
from app.providers.direct import DirectQuoteAdapter
from app.providers.mock import MockLLM, MockMarketData, MockWebSearch


def _aisa_key() -> str | None:
    return os.environ.get("AISA_API_KEY") or None


def _estimate(kind: str) -> int:
    defaults = {"market": 20000, "llm": 10000, "search": 16000}
    return int(
        os.environ.get(f"FINKOW_COST_ESTIMATE_{kind.upper()}_MICROS", defaults[kind])
    )


def _metered(port, tool: str, kind: str):
    """Wrap a paid port: cap-check before, exact debit after."""
    return MeteredPort(
        port,
        ledger=get_ledger(),
        governor=get_governor(),
        tool=tool,
        estimate_micros=_estimate(kind),
    )


def build_market_port() -> MarketDataPort:
    key = _aisa_key()
    if key:
        primary: MarketDataPort = _metered(
            AisaMarketData(key), "aisa.market", "market"
        )
    else:
        primary = MockMarketData()
    chained: MarketDataPort = FallbackMarketData(primary, DirectQuoteAdapter())
    return CachedMarketDataPort(chained)


def build_llm() -> LLMPort:
    key = _aisa_key()
    if key:
        return _metered(AisaLLM(key), "aisa.llm", "llm")
    return MockLLM()


def build_search() -> WebSearchPort:
    key = _aisa_key()
    if key:
        return _metered(AisaWebSearch(key), "aisa.search", "search")
    return MockWebSearch()
