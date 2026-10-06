"""Brokerage port: Alpaca-shaped paper-trading interface.

Shape mirrors Alpaca's paper-trading API (account, positions, market orders)
so a live adapter can slot in later without changing callers.

COMPLIANCE / SAFETY
- ``MockBrokerage`` simulates fills only. No real orders exist in v2.1.
- ``submit_live_order`` always raises ``LiveTradingDisabledError``: the live
  path is intentionally unwired. Enabling it later needs real brokerage keys,
  local securities regulations, and explicit user opt-in — none of which
  exist here.
- Nothing in this module gives financial advice or guarantees returns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import uuid4

from app.money import to_cash, to_qty


class LiveTradingDisabledError(Exception):
    """Raised whenever anyone tries to touch the (unwired) live-trading path."""


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class BrokerageAccount:
    cash: Decimal
    portfolio_value: Decimal
    currency: str = "USD"
    live: bool = False


@dataclass(frozen=True)
class BrokeragePosition:
    symbol: str
    qty: Decimal
    avg_cost: Decimal
    market_value: Decimal


@dataclass(frozen=True)
class BrokerageOrder:
    id: str
    symbol: str
    qty: Decimal
    side: OrderSide
    order_type: str  # "market" for v2.1
    time_in_force: str  # "day" for v2.1
    status: str  # "filled" | "rejected"
    filled_price: Decimal | None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@runtime_checkable
class BrokeragePort(Protocol):
    """Alpaca-shaped paper-trading surface. All async, all simulated."""

    async def get_account(self) -> BrokerageAccount: ...
    async def get_positions(self) -> list[BrokeragePosition]: ...
    async def submit_order(
        self,
        symbol: str,
        qty: Decimal,
        side: OrderSide,
        order_type: str = "market",
        time_in_force: str = "day",
    ) -> BrokerageOrder: ...
    async def get_order(self, order_id: str) -> BrokerageOrder | None: ...
    async def list_orders(self, status: str | None = None) -> list[BrokerageOrder]: ...


def submit_live_order(
    symbol: str,
    qty: Decimal,
    side: OrderSide,
    api_key: str | None = None,
) -> BrokerageOrder:
    """The live-trading path. Intentionally unwired in v2.1 — always raises."""
    raise LiveTradingDisabledError(
        "live trading is disabled: paper simulation only. "
        "Enabling it requires brokerage keys, regulatory review, and explicit opt-in."
    )


def mock_price_fn(symbol: str) -> Decimal:
    """Default price source: the mock market universe (paper only)."""
    from app.providers.mock import _MOCK_UNIVERSE

    try:
        return Decimal(_MOCK_UNIVERSE[symbol.upper().strip()][0])
    except KeyError as exc:
        raise ValueError(f"unknown symbol: {symbol}") from exc


class MockBrokerage:
    """In-memory paper brokerage: market orders fill immediately at the
    injected price function. ``price_fn`` raising ``KeyError``/``ValueError``
    means 'unknown symbol'."""

    def __init__(
        self,
        price_fn=None,
        starting_cash: Decimal = Decimal("100000.00"),
    ) -> None:
        self._price_fn = price_fn or mock_price_fn
        self._cash = to_cash(starting_cash)
        self._positions: dict[str, dict] = {}
        self._orders: list[BrokerageOrder] = []

    def _price(self, symbol: str) -> Decimal:
        try:
            return self._price_fn(symbol)
        except (KeyError, ValueError) as exc:
            raise ValueError(f"unknown symbol: {symbol}") from exc

    async def get_account(self) -> BrokerageAccount:
        return BrokerageAccount(
            cash=self._cash, portfolio_value=self._portfolio_value(), live=False
        )

    async def get_positions(self) -> list[BrokeragePosition]:
        out: list[BrokeragePosition] = []
        for symbol, pos in self._positions.items():
            price = self._price(symbol)
            out.append(
                BrokeragePosition(
                    symbol=symbol,
                    qty=pos["qty"],
                    avg_cost=pos["avg_cost"],
                    market_value=to_cash(pos["qty"] * price),
                )
            )
        return out

    async def submit_order(
        self,
        symbol: str,
        qty: Decimal,
        side: OrderSide,
        order_type: str = "market",
        time_in_force: str = "day",
    ) -> BrokerageOrder:
        symbol = symbol.upper().strip()
        qty = to_qty(qty)
        if qty <= 0:
            raise ValueError("quantity must be positive")
        if side not in (OrderSide.BUY, OrderSide.SELL):
            raise ValueError("side must be buy or sell")
        price = self._price(symbol)
        if side is OrderSide.BUY:
            cost = to_cash(qty * price)
            if cost > self._cash:
                raise ValueError(
                    f"insufficient funds: need ${cost}, have ${self._cash}"
                )
            self._cash = to_cash(self._cash - cost)
            pos = self._positions.get(symbol)
            if pos is None:
                self._positions[symbol] = {"qty": qty, "avg_cost": price}
            else:
                total_qty = pos["qty"] + qty
                pos["avg_cost"] = to_cash(
                    (pos["avg_cost"] * pos["qty"] + price * qty) / total_qty
                )
                pos["qty"] = total_qty
        else:
            pos = self._positions.get(symbol)
            if pos is None or pos["qty"] < qty:
                have = pos["qty"] if pos else Decimal("0")
                raise ValueError(
                    f"insufficient position: have {have} {symbol}, need {qty}"
                )
            proceeds = to_cash(qty * price)
            self._cash = to_cash(self._cash + proceeds)
            pos["qty"] = to_qty(pos["qty"] - qty)
            if pos["qty"] <= 0:
                del self._positions[symbol]
        order = BrokerageOrder(
            id=uuid4().hex[:12],
            symbol=symbol,
            qty=qty,
            side=side,
            order_type=order_type,
            time_in_force=time_in_force,
            status="filled",
            filled_price=price,
        )
        self._orders.append(order)
        return order

    async def get_order(self, order_id: str) -> BrokerageOrder | None:
        for order in self._orders:
            if order.id == order_id:
                return order
        return None

    async def list_orders(self, status: str | None = None) -> list[BrokerageOrder]:
        if status is None:
            return list(self._orders)
        return [o for o in self._orders if o.status == status]

    def _portfolio_value(self) -> Decimal:
        total = self._cash
        for symbol, pos in self._positions.items():
            total += pos["qty"] * self._price(symbol)
        return to_cash(total)
