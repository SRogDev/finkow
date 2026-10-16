"""Phase-1 AI stub: grounded portfolio explanations.

The answer is always computed from real structured data (the portfolio view).
If OPENROUTER_API_KEY is set, an LLM only *rephrases* that grounded summary —
it never invents numbers. On any failure we fall back to the deterministic text.

This is intentionally not an agent. Phase 2 wires the full conversational
interface; the contract here (structured ops, never direct DB mutation) stays.
"""

from __future__ import annotations

import os

import httpx

from app.money import cash_str, qty_str
from app.portfolio import PortfolioView

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"


def build_grounded_summary(pv: PortfolioView) -> str:
    """Deterministic, numbers-only summary. The single source of truth."""
    direction = "up" if pv.total_return >= 0 else "down"
    lines = [
        f"Your portfolio is worth ${cash_str(pv.total_value)} "
        f"({direction} ${cash_str(abs(pv.total_return))}, "
        f"{pv.total_return_pct}% since you started with "
        f"${cash_str(pv.initial_cash)} virtual cash).",
        f"Cash: ${cash_str(pv.cash)}.",
    ]
    if not pv.positions:
        lines.append("You hold no positions yet — your money is 100% in cash.")
        return " ".join(lines)
    movers = sorted(pv.positions, key=lambda p: p.unrealized_pnl, reverse=True)
    for p in movers:
        gain_word = "gained" if p.unrealized_pnl >= 0 else "lost"
        stale_note = " (price may be stale)" if p.stale else ""
        lines.append(
            f"{p.symbol}: {qty_str(p.qty)} @ avg ${cash_str(p.avg_cost)}, now "
            f"${cash_str(p.price)}{stale_note} — {gain_word} "
            f"${cash_str(abs(p.unrealized_pnl))} ({p.unrealized_pnl_pct}%)."
        )
    best, worst = movers[0], movers[-1]
    if len(movers) > 1 and best.unrealized_pnl != worst.unrealized_pnl:
        lines.append(
            f"Biggest contributor: {best.symbol} (+${cash_str(best.unrealized_pnl)}); "
            f"biggest drag: {worst.symbol} (${cash_str(worst.unrealized_pnl)})."
        )
    return " ".join(lines)


async def _polish_with_openrouter(summary: str, question: str) -> str | None:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "HTTP-Referer": "https://github.com/SRogDev/finkow",
                    "X-Title": "Finkow",
                },
                json={
                    "model": os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL),
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You explain a virtual-money investing sandbox portfolio. "
                                "Use ONLY the numbers in the portfolio facts. Never invent "
                                "prices, returns, or positions. Keep it short and plain."
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"Question: {question}\n\nPortfolio facts:\n{summary}",
                        },
                    ],
                },
            )
            resp.raise_for_status()
            return str(resp.json()["choices"][0]["message"]["content"]).strip()
    except Exception:
        return None


async def explain_portfolio(pv: PortfolioView, question: str) -> dict:
    summary = build_grounded_summary(pv)
    polished = await _polish_with_openrouter(summary, question)
    if polished:
        return {
            "answer": polished,
            "grounded": True,
            "model": os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL),
        }
    return {"answer": summary, "grounded": True, "model": "finkow-stub"}
