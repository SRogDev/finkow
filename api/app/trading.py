"""Paper-trade execution: the single place where positions change.

Extracted verbatim from the v1 order endpoint so the HTTP layer and the
PortfolioPilot agent share identical math. Paper money only — there is no
real-money code path anywhere in this service.
"""

from __future__ import annotations

from decimal import Decimal

from app.money import cash_str, qty_str, to_cash, to_qty
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
) -> Transaction:
    """Buy ``qty`` of ``symbol`` at ``price`` with virtual cash."""
    if qty <= 0:
        raise ValueError("quantity must be positive")
    account = store.get_account(account_id)
    if account is None:
        raise ValueError(f"account not found: {account_id}")
    sym = symbol.upper().strip()
    qty = to_qty(qty)
    cost = to_cash(price * qty)
    if cost > account.cash:
        raise InsufficientFundsError(
            f"insufficient funds: need ${cash_str(cost)}, have ${cash_str(account.cash)}"
        )
    account.cash = to_cash(account.cash - cost)
    position = store.get_position(account.id, sym)
    if position is None:
        position = Position(
            account_id=account.id, symbol=sym, qty=qty, avg_cost=to_cash(price)
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
    )
    store.add_transaction(txn)
    return txn


def execute_paper_sell(
    store: InMemoryStore,
    account_id: str,
    symbol: str,
    qty: Decimal,
    price: Decimal,
) -> Transaction:
    """Sell ``qty`` of ``symbol`` at ``price`` back into virtual cash."""
    if qty <= 0:
        raise ValueError("quantity must be positive")
    account = store.get_account(account_id)
    if account is None:
        raise ValueError(f"account not found: {account_id}")
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
    )
    store.add_transaction(txn)
    return txn
