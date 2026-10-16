"""Explainer: grounded "what happened / why" for portfolios and agent actions.

The answer is computed from real structured data first (portfolio view,
snapshots, fresh headlines via the search port); the LLM port only renders it
in plain language. Numbers are never invented: if the LLM is unavailable the
deterministic grounded summary is returned as-is.
"""

from __future__ import annotations

from app.agents.events import EventLog
from app.governance.metering import CreditsExhausted
from app.money import cash_str, qty_str
from app.portfolio import PortfolioView, value_portfolio
from app.ports import ChatMessage, LLMPort, MarketDataPort, ProviderError, WebSearchPort
from app.store import InMemoryStore

TASK_MARKER = "[finkow-task: explain]"

_SYSTEM_PROMPT = (
    f"{TASK_MARKER} You answer questions about a virtual-money (paper trading) "
    "portfolio. Use ONLY the numbers in PORTFOLIO FACTS and the headlines in "
    "HEADLINES. Never invent prices, returns, or positions. Plain language, "
    "zero jargon, short. This is paper money."
)


class Explainer:
    """Answers portfolio questions, grounded in real computed data."""

    def __init__(
        self,
        store: InMemoryStore,
        market: MarketDataPort,
        llm: LLMPort,
        search: WebSearchPort,
        events: EventLog | None = None,
    ) -> None:
        self._store = store
        self._market = market
        self._llm = llm
        self._search = search
        self._events = events or EventLog()

    async def explain(self, account_id: str, question: str) -> dict:
        account = self._store.get_account(account_id)
        if account is None:
            raise ValueError(f"account not found: {account_id}")
        positions = self._store.get_positions(account_id)
        quotes = {}
        for pos in positions:
            try:
                quotes[pos.symbol] = await self._market.get_quote(pos.symbol)
            except CreditsExhausted:
                raise
            except ProviderError:
                continue
        pv = value_portfolio(account, positions, quotes)
        facts = self._grounded_facts(pv)
        headlines = await self._headlines(pv)
        try:
            answer = await self._llm.complete(
                [
                    ChatMessage(
                        role="user",
                        content=(
                            f"QUESTION: {question.strip()[:500]}\n\n"
                            f"PORTFOLIO FACTS:\n{facts}\n\nHEADLINES:\n{headlines}"
                        ),
                    )
                ],
                system=_SYSTEM_PROMPT,
            )
            model = self._llm.name
        except CreditsExhausted:
            raise
        except ProviderError:
            answer, model = facts, "finkow-grounded"
        self._events.append(
            "explainer",
            "explainer.answered",
            {"account_id": account_id, "question": question[:200]},
        )
        return {"answer": answer, "grounded": True, "model": model}

    def _grounded_facts(self, pv: PortfolioView) -> str:
        direction = "up" if pv.total_return >= 0 else "down"
        lines = [
            f"Total value ${cash_str(pv.total_value)} ({direction} "
            f"${cash_str(abs(pv.total_return))}, {pv.total_return_pct}% "
            f"from ${cash_str(pv.initial_cash)} starting virtual cash).",
            f"Cash on hand ${cash_str(pv.cash)}.",
        ]
        snapshots = self._store.list_snapshots(pv.account_id)
        if len(snapshots) >= 2:
            first, last = snapshots[0].total_value, snapshots[-1].total_value
            move = last - first
            move_dir = "up" if move >= 0 else "down"
            lines.append(
                f"Since the first recorded snapshot the portfolio moved {move_dir} "
                f"${cash_str(abs(move))} (from ${cash_str(first)} to ${cash_str(last)})."
            )
        if not pv.positions:
            lines.append("No positions held — everything is in cash.")
            return " ".join(lines)
        for p in sorted(pv.positions, key=lambda x: x.unrealized_pnl, reverse=True):
            word = "gained" if p.unrealized_pnl >= 0 else "lost"
            stale = " (price may be stale)" if p.stale else ""
            lines.append(
                f"{p.symbol}: {qty_str(p.qty)} at avg ${cash_str(p.avg_cost)}, now "
                f"${cash_str(p.price)}{stale} — {word} ${cash_str(abs(p.unrealized_pnl))} "
                f"({p.unrealized_pnl_pct}%)."
            )
        return " ".join(lines)

    async def _headlines(self, pv: PortfolioView) -> str:
        top = sorted(pv.positions, key=lambda p: p.market_value, reverse=True)[:2]
        lines: list[str] = []
        for p in top:
            try:
                results = await self._search.search(f"{p.symbol} stock news", max_results=2)
            except CreditsExhausted:
                raise
            except ProviderError:
                continue
            for r in results:
                lines.append(f"- {p.symbol}: {r.title}")
        return "\n".join(lines) if lines else "No fresh headlines available."
