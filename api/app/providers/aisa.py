"""AIsa gateway adapters (https://aisa.one).

One API key (``AISA_API_KEY``) for models, market data, and web search.
Endpoint shapes follow AIsa's public skill docs; parsing is defensive on
purpose. These adapters are implemented against documentation and mock
transports only — they have NOT been exercised against the live gateway.
Live verification with a real key is still pending.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

import httpx

from app.market import Quote, SymbolNotFound, build_client
from app.ports import (
    ChatMessage,
    Fundamentals,
    NewsItem,
    ProviderError,
    SearchResult,
)

BASE = "https://api.aisa.one"
DEFAULT_MODEL = os.environ.get("AISA_MODEL", "gpt-4o-mini")


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _close_of_bar(bar: dict) -> Decimal | None:
    for key in ("close", "c", "price", "usd"):
        if key in bar and bar[key] is not None:
            try:
                return Decimal(str(bar[key]))
            except (InvalidOperation, ValueError):
                continue
    return None


def _bar_list(payload: object) -> list[dict] | None:
    """Find the list of price bars in a response, tolerating key variations."""
    if isinstance(payload, list):
        return [b for b in payload if isinstance(b, dict)] or None
    if isinstance(payload, dict):
        for key in ("data", "prices", "bars", "result", "items"):
            bars = _bar_list(payload.get(key))
            if bars:
                return bars
    return None


class AisaMarketData:
    """Stocks/crypto quotes (and best-effort fundamentals) via AIsa."""

    name = "aisa"

    def __init__(
        self,
        api_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._key = api_key
        self._client = client or build_client()

    async def get_quote(self, symbol: str) -> Quote:
        sym = symbol.upper().strip()
        if not sym:
            raise SymbolNotFound(symbol)
        end = datetime.now(UTC).date()
        start = end - timedelta(days=7)
        url = (
            f"{BASE}/apis/v1/financial/prices"
            f"?ticker={sym}&interval=day&interval_multiplier=1"
            f"&start_date={start.isoformat()}&end_date={end.isoformat()}"
        )
        try:
            resp = await self._client.get(url, headers=_auth_headers(self._key), timeout=15.0)
        except httpx.HTTPError as exc:
            raise ProviderError(f"aisa market data unreachable: {exc}") from exc
        if resp.status_code == 404:
            raise SymbolNotFound(sym)
        try:
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            raise ProviderError(f"aisa market data bad response: {exc}") from exc
        bars = _bar_list(payload)
        closes = [c for c in (_close_of_bar(b) for b in bars or []) if c is not None]
        if not closes:
            # Unknown shape or unknown ticker: surface as not-found only when
            # the gateway says so explicitly; otherwise it is a provider error
            # so the fallback chain can try the direct providers.
            raise ProviderError(f"aisa: no usable price bars for {sym}")
        return Quote(
            symbol=sym,
            price=closes[-1],
            currency="USD",
            as_of=datetime.now(UTC),
            provider=self.name,
        )

    async def get_fundamentals(self, symbol: str) -> Fundamentals | None:
        # No verified fundamentals endpoint in the public docs yet; the news/
        # research leg is covered by the WebSearch port. Return None (honest
        # "unknown") rather than inventing numbers.
        return None

    async def get_news(self, symbol: str, limit: int = 5) -> list[NewsItem]:
        # Covered by WebSearchPort (Tavily via AIsa) instead.
        return []


class AisaLLM:
    """Chat completions through AIsa's OpenAI-compatible gateway."""

    name = "aisa"

    def __init__(
        self,
        api_key: str,
        client: httpx.AsyncClient | None = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._key = api_key
        self._client = client or build_client()
        self.model = model

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        system: str = "",
        json_mode: bool = False,
    ) -> str:
        payload_messages: list[dict[str, str]] = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend({"role": m.role, "content": m.content} for m in messages)
        body: dict = {"model": self.model, "messages": payload_messages}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            resp = await self._client.post(
                f"{BASE}/v1/chat/completions",
                headers=_auth_headers(self._key),
                json=body,
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return str(data["choices"][0]["message"]["content"]).strip()
        except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"aisa llm failed: {exc}") from exc


class AisaWebSearch:
    """Web search via Tavily through the AIsa gateway.

    Endpoint mapping is best-effort from AIsa's public skill docs
    (``/tavily/crawl`` and ``/tavily/extract`` are documented there; search
    follows the same ``/apis/v1`` pattern). Verify against the live gateway
    with a real key before relying on it.
    """

    name = "aisa"

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None) -> None:
        self._key = api_key
        self._client = client or build_client()

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        try:
            resp = await self._client.post(
                f"{BASE}/apis/v1/tavily/search",
                headers=_auth_headers(self._key),
                json={"query": query, "max_results": max_results},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"aisa web search failed: {exc}") from exc
        raw = data.get("results", []) if isinstance(data, dict) else []
        out: list[SearchResult] = []
        for item in raw[:max_results]:
            if not isinstance(item, dict):
                continue
            out.append(
                SearchResult(
                    title=str(item.get("title", "")),
                    url=str(item.get("url", "")),
                    snippet=str(item.get("content", item.get("snippet", ""))),
                    source="tavily",
                )
            )
        return out
