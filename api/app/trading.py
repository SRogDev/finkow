"""Paper-trade execution: the single place where positions change.

Extracted verbatim from the v1 order endpoint so the HTTP layer and the
PortfolioPilot agent share identical math. Paper money only — there is no
real-money code path anywhere in this service.
"""

from __future__ import annotations

from decimal import Decimal

from app.brokerage import LiveTradingDisabledError
from app.modes import REAL_NOT_CONFIGURED, Mode, check_mode
from app.money import cash_str, qty_str, to_cash, to_qty
from app.orders import OrderStatus
from app.portfolio import average_cost, unrealized_pnl
from app.store import InMemoryStore, Position, Transaction, new_id, utcnow


class InsufficientFundsError(Exception):
    """Buy cost exceeds available cash."""


class InsufficientPositionError(Exception):
    """Sell quantity exceeds the held position."""


def execute_paper_buy(
    store: InMemoryStore,
    account_id: str,
    symbol: str,
    qty: Decimal,
    price: Decimal,
    *,
    mode: Mode = Mode.EXPERIMENTAL,
    order_id: str | None = None,
) -> Transaction:
    """Buy ``qty`` of ``symbol`` at ``price`` with virtual cash.

    Mode-gated: the operation's mode must match the account's mode
    (``CrossModeError`` otherwise), and ``Mode.REAL`` always raises
    ``LiveTradingDisabledError`` — real execution is not configured, and
    this function never simulates it.

    ``order_id`` links the fill back to its lifecycle order. The resulting
    transaction is always marked ``simulated=True``: paper fills are never
    real execution records.
    """
    if qty <= 0:
        raise ValueError("quantity must be positive")
    account = store.get_account(account_id)
    if account is None:
        raise ValueError(f"account not found: {account_id}")
    check_mode(account.mode, mode, f"buy {symbol} on account {account_id}")
    if mode is Mode.REAL:
        raise LiveTradingDisabledError(REAL_NOT_CONFIGURED)
    sym = symbol.upper().strip()
    qty = to_qty(qty)
    cost = to_cash(price * qty)
    if cost > account.cash:
        raise InsufficientFundsError(
            f"insufficient funds: need ${cash_str(cost)}, have ${cash_str(account.cash)}"
        )
    account.cash = to_cash(account.cash - cost)
    store.save_account(account)
    position = store.get_position(account.id, sym)
    if position is None:
        position = Position(
            account_id=account.id, symbol=sym, qty=qty, avg_cost=to_cash(price),
            mode=account.mode,
        )
    else:
        position.avg_cost = average_cost(position.qty, position.avg_cost, qty, price)
        position.qty = to_qty(position.qty + qty)
    store.upsert_position(position)
    txn = Transaction(
        id=new_id(),
        account_id=account.id,
        symbol=sym,
        side="buy",
        qty=qty,
        price=price,
        cash_delta=-cost,
        realized_pnl=None,
        created_at=utcnow(),
        mode=account.mode,
        order_id=order_id,
        status=OrderStatus.FILLED,
        simulated=True,
    )
    store.add_transaction(txn)
    return txn


def execute_paper_sell(
    store: InMemoryStore,
    account_id: str,
    symbol: str,
    qty: Decimal,
    price: Decimal,
    *,
    mode: Mode = Mode.EXPERIMENTAL,
    order_id: str | None = None,
) -> Transaction:
    """Sell ``qty`` of ``symbol`` at ``price`` back into virtual cash.

    Same mode gating as :func:`execute_paper_buy`.
    """
    if qty <= 0:
        raise ValueError("quantity must be positive")
    account = store.get_account(account_id)
    if account is None:
        raise ValueError(f"account not found: {account_id}")
    check_mode(account.mode, mode, f"sell {symbol} on account {account_id}")
    if mode is Mode.REAL:
        raise LiveTradingDisabledError(REAL_NOT_CONFIGURED)
    sym = symbol.upper().strip()
    qty = to_qty(qty)
    position = store.get_position(account.id, sym)
    if position is None or position.qty < qty:
        have = qty_str(position.qty) if position else "0"
        raise InsufficientPositionError(
            f"insufficient position: trying to sell {qty_str(qty)} {sym}, hold {have}"
        )
    proceeds = to_cash(price * qty)
    realized = unrealized_pnl(qty, position.avg_cost, price)
    account.cash = to_cash(account.cash + proceeds)
    store.save_account(account)
    remaining = to_qty(position.qty - qty)
    if remaining == 0:
        store.remove_position(account.id, sym)
    else:
        position.qty = remaining
        store.upsert_position(position)
    txn = Transaction(
        id=new_id(),
        account_id=account.id,
        symbol=sym,
        side="sell",
        qty=qty,
        price=price,
        cash_delta=proceeds,
        realized_pnl=realized,
        created_at=utcnow(),
        mode=account.mode,
        order_id=order_id,
        status=OrderStatus.FILLED,
        simulated=True,
    )
    store.add_transaction(txn)
    return txn
