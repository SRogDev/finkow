"""Domain records + storage interface.

InMemoryStore backs the MVP scaffold and the test suite. The Supabase adapter
(schema in supabase/schema.sql) implements the same Store protocol later —
domain code never touches storage details directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from uuid import uuid4

STARTING_CASH = Decimal("100000.00")


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid4().hex[:12]


@dataclass
class Account:
    id: str
    email: str | None
    cash: Decimal
    initial_cash: Decimal
    created_at: datetime


@dataclass
class Position:
    account_id: str
    symbol: str
    qty: Decimal
    avg_cost: Decimal


@dataclass
class Transaction:
    id: str
    account_id: str
    symbol: str
    side: str  # "buy" | "sell"
    qty: Decimal
    price: Decimal
    cash_delta: Decimal  # negative on buy, positive on sell
    realized_pnl: Decimal | None  # set on sells
    created_at: datetime


@dataclass
class Snapshot:
    account_id: str
    total_value: Decimal
    cash: Decimal
    created_at: datetime


@dataclass(frozen=True)
class Goal:
    id: str
    text: str
    amount: Decimal
    account_id: str
    created_at: datetime


class Store(Protocol):
    def create_account(self, email: str | None, initial_cash: Decimal = ...) -> Account: ...
    def get_account(self, account_id: str) -> Account | None: ...
    def get_positions(self, account_id: str) -> list[Position]: ...
    def get_position(self, account_id: str, symbol: str) -> Position | None: ...
    def upsert_position(self, position: Position) -> None: ...
    def remove_position(self, account_id: str, symbol: str) -> None: ...
    def add_transaction(self, txn: Transaction) -> None: ...
    def list_transactions(self, account_id: str) -> list[Transaction]: ...
    def add_snapshot(self, snapshot: Snapshot) -> None: ...
    def list_snapshots(self, account_id: str) -> list[Snapshot]: ...
    def create_goal(self, text: str, amount: Decimal, account_id: str) -> Goal: ...
    def get_goal(self, goal_id: str) -> Goal | None: ...
    def save_plan(self, goal_id: str, plan: dict) -> None: ...
    def get_plan(self, goal_id: str) -> dict | None: ...


class InMemoryStore:
    """Volatile store for the scaffold. Swap for SupabaseStore in Phase 2."""

    def __init__(self) -> None:
        self.accounts: dict[str, Account] = {}
        self.positions: dict[tuple[str, str], Position] = {}
        self.transactions: list[Transaction] = []
        self.snapshots: list[Snapshot] = []
        self.goals: dict[str, Goal] = {}
        self.plans: dict[str, dict] = {}

    def create_account(
        self, email: str | None, initial_cash: Decimal = STARTING_CASH
    ) -> Account:
        account = Account(
            id=new_id(),
            email=email,
            cash=initial_cash,
            initial_cash=initial_cash,
            created_at=utcnow(),
        )
        self.accounts[account.id] = account
        return account

    def get_account(self, account_id: str) -> Account | None:
        return self.accounts.get(account_id)

    def get_positions(self, account_id: str) -> list[Position]:
        return [p for (aid, _), p in self.positions.items() if aid == account_id]

    def get_position(self, account_id: str, symbol: str) -> Position | None:
        return self.positions.get((account_id, symbol))

    def upsert_position(self, position: Position) -> None:
        self.positions[(position.account_id, position.symbol)] = position

    def remove_position(self, account_id: str, symbol: str) -> None:
        self.positions.pop((account_id, symbol), None)

    def add_transaction(self, txn: Transaction) -> None:
        self.transactions.append(txn)

    def list_transactions(self, account_id: str) -> list[Transaction]:
        return [t for t in self.transactions if t.account_id == account_id]

    def add_snapshot(self, snapshot: Snapshot) -> None:
        self.snapshots.append(snapshot)

    def list_snapshots(self, account_id: str) -> list[Snapshot]:
        return [s for s in self.snapshots if s.account_id == account_id]

    def create_goal(self, text: str, amount: Decimal, account_id: str) -> Goal:
        goal = Goal(
            id=new_id(),
            text=text,
            amount=amount,
            account_id=account_id,
            created_at=utcnow(),
        )
        self.goals[goal.id] = goal
        return goal

    def get_goal(self, goal_id: str) -> Goal | None:
        return self.goals.get(goal_id)

    def save_plan(self, goal_id: str, plan: dict) -> None:
        self.plans[goal_id] = plan

    def get_plan(self, goal_id: str) -> dict | None:
        return self.plans.get(goal_id)
