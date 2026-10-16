"""Domain records + storage interface.

InMemoryStore backs the MVP scaffold and the test suite. The Supabase adapter
(schema in supabase/schema.sql) implements the same Store protocol later —
domain code never touches storage details directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.ids import new_id, utcnow
from app.modes import Mode
from app.orders import Order, OrderStatus

STARTING_CASH = Decimal("100000.00")


# (utcnow/new_id live in app.ids; re-exported here so existing
# ``from app.store import utcnow, new_id`` imports keep working.)


@dataclass
class Account:
    id: str
    email: str | None
    cash: Decimal
    initial_cash: Decimal
    created_at: datetime
    owner_user_id: str = ""  # Supabase auth.users id; "" only for pre-ownership data
    mode: Mode = Mode.EXPERIMENTAL  # Mode.REAL has no execution path wired


@dataclass
class Position:
    account_id: str
    symbol: str
    qty: Decimal
    avg_cost: Decimal
    mode: Mode = Mode.EXPERIMENTAL


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
    mode: Mode = Mode.EXPERIMENTAL
    # Order-lifecycle linkage (Phase 4). Every paper fill links back to its
    # order; ``simulated=True`` marks mock fills so they can never be
    # presented as real execution.
    order_id: str | None = None
    status: OrderStatus = OrderStatus.FILLED
    simulated: bool = True


@dataclass
class Snapshot:
    account_id: str
    total_value: Decimal
    cash: Decimal
    created_at: datetime
    mode: Mode = Mode.EXPERIMENTAL


@dataclass(frozen=True)
class Goal:
    id: str
    text: str
    amount: Decimal
    account_id: str
    created_at: datetime


@dataclass
class UserProfile:
    """The LearningAgent's picture of the user: risk, horizon, preferences,
    and a short decision history. One per account."""

    account_id: str
    risk: str = "medium"  # "low" | "medium" | "high"
    horizon_years: float = 5.0
    preferences: dict = field(default_factory=dict)
    updated_at: datetime = field(default_factory=utcnow)


@dataclass
class ApprovalRequest:
    """A pending human-confirmation decision for money movement.

    Created by the InvestmentExecutor's propose step; resolved by confirm.
    ``trades`` is a list of plain dicts (symbol/side/qty/est_price) so the
    user sees exactly what they approve.
    """

    account_id: str
    trades: list[dict]
    total_usd: Decimal
    status: str = "pending"  # "pending" | "approved" | "rejected" | "expired"
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)
    decided_at: datetime | None = None
    mode: Mode = Mode.EXPERIMENTAL


class Store(Protocol):
    def create_account(
        self,
        email: str | None,
        initial_cash: Decimal = ...,
        owner_user_id: str = ...,
        mode: Mode = ...,
    ) -> Account: ...
    def get_account(self, account_id: str) -> Account | None: ...
    def list_accounts_by_owner(self, owner_user_id: str) -> list[Account]:
        """All accounts owned by a user (for per-user limits)."""
        ...
    def save_account(self, account: Account) -> None:
        """Persist account mutations (e.g. cash balance changes).

        In-memory stores may no-op on identity; durable stores must write
        the row back — mutating the returned object is not enough.
        """
        ...
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
    def get_profile(self, account_id: str) -> UserProfile | None: ...
    def save_profile(self, profile: UserProfile) -> UserProfile: ...
    def save_approval(self, request: ApprovalRequest) -> ApprovalRequest: ...
    def get_approval(self, approval_id: str) -> ApprovalRequest | None: ...
    def list_approvals(
        self, account_id: str, status: str | None = ...
    ) -> list[ApprovalRequest]: ...
    # -- orders (explicit lifecycle) ---------------------------------
    def save_order(self, order: Order) -> None:
        """Insert or update an order (upsert by id)."""
        ...
    def get_order(self, order_id: str) -> Order | None: ...
    def get_order_by_idempotency_key(
        self, account_id: str, key: str
    ) -> Order | None: ...
    def list_orders(
        self, account_id: str, status: OrderStatus | None = ...
    ) -> list[Order]: ...


class InMemoryStore:
    """Volatile store for the scaffold. Swap for SupabaseStore in Phase 2."""

    def __init__(self) -> None:
        self.accounts: dict[str, Account] = {}
        self.positions: dict[tuple[str, str], Position] = {}
        self.transactions: list[Transaction] = []
        self.snapshots: list[Snapshot] = []
        self.goals: dict[str, Goal] = {}
        self.plans: dict[str, dict] = {}
        self.profiles: dict[str, UserProfile] = {}
        self.approvals: dict[str, ApprovalRequest] = {}
        self.orders: dict[str, Order] = {}
        self.orders_by_idempotency: dict[tuple[str, str], str] = {}

    def create_account(
        self,
        email: str | None,
        initial_cash: Decimal = STARTING_CASH,
        owner_user_id: str = "",
        mode: Mode = Mode.EXPERIMENTAL,
    ) -> Account:
        account = Account(
            id=new_id(),
            email=email,
            cash=initial_cash,
            initial_cash=initial_cash,
            created_at=utcnow(),
            owner_user_id=owner_user_id,
            mode=mode,
        )
        self.accounts[account.id] = account
        return account

    def get_account(self, account_id: str) -> Account | None:
        return self.accounts.get(account_id)

    def list_accounts_by_owner(self, owner_user_id: str) -> list[Account]:
        return [
            a for a in self.accounts.values()
            if a.owner_user_id == owner_user_id
        ]

    def save_account(self, account: Account) -> None:
        self.accounts[account.id] = account

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

    def get_profile(self, account_id: str) -> UserProfile | None:
        return self.profiles.get(account_id)

    def save_profile(self, profile: UserProfile) -> UserProfile:
        profile.updated_at = utcnow()
        self.profiles[profile.account_id] = profile
        return profile

    def save_approval(self, request: ApprovalRequest) -> ApprovalRequest:
        self.approvals[request.id] = request
        return request

    def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        return self.approvals.get(approval_id)

    def list_approvals(
        self, account_id: str, status: str | None = None
    ) -> list[ApprovalRequest]:
        return [
            r
            for r in self.approvals.values()
            if r.account_id == account_id and (status is None or r.status == status)
        ]

    # -- orders ------------------------------------------------------

    def save_order(self, order: Order) -> None:
        self.orders[order.id] = order
        if order.idempotency_key:
            self.orders_by_idempotency[
                (order.account_id, order.idempotency_key)
            ] = order.id

    def get_order(self, order_id: str) -> Order | None:
        return self.orders.get(order_id)

    def get_order_by_idempotency_key(
        self, account_id: str, key: str
    ) -> Order | None:
        order_id = self.orders_by_idempotency.get((account_id, key))
        return self.orders.get(order_id) if order_id else None

    def list_orders(
        self, account_id: str, status: OrderStatus | None = None
    ) -> list[Order]:
        return [
            o
            for o in self.orders.values()
            if o.account_id == account_id
            and (status is None or o.status is status)
        ]
