"""Provider ports: the seams every Finkow v2 agent programs against.

Three ports, dependency-injected:
- ``MarketDataPort`` — quotes, fundamentals, news. Every market fact an agent
  uses must come through here. No hardcoded prices anywhere else.
- ``LLMPort`` — chat completions. Every AI-generated sentence goes through here.
- ``WebSearchPort`` — web search results.

Implementations live in ``app/providers/``: ``mock`` (deterministic, for tests
and demos without a key), ``aisa`` (AIsa gateway, needs ``AISA_API_KEY``), and
``direct`` (free keyless quote fallback). ``cached`` adds TTL quote caching on
top of any market-data port.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.market import Quote  # re-exported: the v1 quote type is the port type


class ProviderError(Exception):
    """A provider failed in a way the caller may want to fall back from."""


class ProviderNotSupported(ProviderError):
    """The provider does not implement this capability at all."""


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "user" | "assistant" (system goes via the system= kwarg)
    content: str


@dataclass(frozen=True)
class Fundamentals:
    symbol: str
    name: str
    sector: str
    pe_ratio: Decimal | None
    market_cap_usd: Decimal | None


@dataclass(frozen=True)
class NewsItem:
    symbol: str
    headline: str
    source: str
    published_at: datetime | None = None
    url: str | None = None


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = ""


class MarketDataPort(Protocol):
    name: str

    async def get_quote(self, symbol: str) -> Quote: ...
    async def get_fundamentals(self, symbol: str) -> Fundamentals | None: ...
    async def get_news(self, symbol: str, limit: int = 5) -> list[NewsItem]: ...


class LLMPort(Protocol):
    name: str

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        system: str = "",
        json_mode: bool = False,
    ) -> str: ...


class WebSearchPort(Protocol):
    name: str

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]: ...
