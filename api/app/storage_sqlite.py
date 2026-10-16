"""SQLite-backed durable storage.

One file (``FINKOW_DB_PATH``, default ``data/finkow.db`` under the api dir)
holds the domain store, the audit log, the agent event log, and the credits
ledger — a restart no longer erases financial history.

Atomicity: every mutating call runs inside a single SQLite transaction under
a process-wide lock (WAL journaling), so concurrent requests cannot
interleave half-written rows. Decimals are stored as TEXT, datetimes as ISO
strings — no float money, ever.

This is a file, not a new database service: zero new infrastructure, and the
Store protocol keeps domain code storage-agnostic (Supabase later).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.billing.credits import CreditEntry
from app.governance.audit import AuditEntry
from app.modes import Mode
from app.orders import Order, OrderStatus
from app.store import (
    STARTING_CASH,
    Account,
    ApprovalRequest,
    Goal,
    Position,
    Snapshot,
    Transaction,
    UserProfile,
    new_id,
    utcnow,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    email TEXT,
    cash TEXT NOT NULL,
    initial_cash TEXT NOT NULL,
    owner_user_id TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT 'experimental',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS positions (
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    qty TEXT NOT NULL,
    avg_cost TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'experimental',
    PRIMARY KEY (account_id, symbol)
);
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty TEXT NOT NULL,
    price TEXT NOT NULL,
    cash_delta TEXT NOT NULL,
    realized_pnl TEXT,
    mode TEXT NOT NULL DEFAULT 'experimental',
    order_id TEXT,
    status TEXT NOT NULL DEFAULT 'filled',
    simulated INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_id);
CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    total_value TEXT NOT NULL,
    cash TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'experimental',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_account ON snapshots(account_id);
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    amount TEXT NOT NULL,
    account_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
    goal_id TEXT PRIMARY KEY,
    plan_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profiles (
    account_id TEXT PRIMARY KEY,
    risk TEXT NOT NULL,
    horizon_years REAL NOT NULL,
    preferences_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    trades_json TEXT NOT NULL,
    total_usd TEXT NOT NULL,
    status TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'experimental',
    created_at TEXT NOT NULL,
    decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_approvals_account ON approvals(account_id);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty TEXT NOT NULL,
    order_type TEXT NOT NULL DEFAULT 'market',
    time_in_force TEXT NOT NULL DEFAULT 'day',
    status TEXT NOT NULL DEFAULT 'draft',
    filled_qty TEXT NOT NULL DEFAULT '0',
    avg_fill_price TEXT,
    provider_order_id TEXT,
    simulated INTEGER NOT NULL DEFAULT 1,
    idempotency_key TEXT,
    approval_id TEXT,
    reject_reason TEXT,
    mode TEXT NOT NULL DEFAULT 'experimental',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orders_account ON orders(account_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_idempotency
    ON orders(account_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE TABLE IF NOT EXISTS audit_entries (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    account_id TEXT,
    outcome TEXT NOT NULL,
    details_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_account_action
    ON audit_entries(account_id, action);
CREATE TABLE IF NOT EXISTS agent_events (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    agent TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_agent ON agent_events(agent);
CREATE TABLE IF NOT EXISTS credit_entries (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    account_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    credits INTEGER NOT NULL,
    tool TEXT NOT NULL,
    meta_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_credits_account ON credit_entries(account_id);
CREATE TABLE IF NOT EXISTS credit_sessions (
    session_id TEXT PRIMARY KEY
);
"""


def _dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """Add a column to an existing table only if it is missing — lets
    databases created before a schema change keep working."""
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


class SqliteBackend:
    """A single SQLite connection + schema + process-wide write lock."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._local = threading.local()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)
            # migrate databases created before the order-lifecycle columns
            _ensure_column(self._conn, "transactions", "order_id", "TEXT")
            _ensure_column(
                self._conn, "transactions", "status",
                "TEXT NOT NULL DEFAULT 'filled'",
            )
            _ensure_column(
                self._conn, "transactions", "simulated",
                "INTEGER NOT NULL DEFAULT 1",
            )
            # index on the migrated column, once it exists
            cols = {
                r["name"]
                for r in self._conn.execute("PRAGMA table_info(transactions)")
            }
            if "order_id" in cols:
                self._conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_transactions_order"
                    " ON transactions(order_id)"
                )
            self._conn.commit()

    def run(self, fn):
        """Run ``fn(conn)`` atomically under the lock; commit or roll back.

        Nested ``run`` calls are a programming error (the lock is not
        reentrant) and raise immediately instead of deadlocking.
        """
        if getattr(self._local, "in_run", False):
            raise RuntimeError(
                "nested SqliteBackend.run() call — restructure to a single"
                " transaction instead of deadlocking"
            )
        self._local.in_run = True
        with self._lock:
            try:
                result = fn(self._conn)
                self._conn.commit()
                return result
            except Exception:
                self._conn.rollback()
                raise
            finally:
                self._local.in_run = False

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ---------------------------------------------------------------- row mapping


def _account_row(row: sqlite3.Row) -> Account:
    return Account(
        id=row["id"],
        email=row["email"],
        cash=Decimal(row["cash"]),
        initial_cash=Decimal(row["initial_cash"]),
        created_at=_dt(row["created_at"]),
        owner_user_id=row["owner_user_id"] or "",
        mode=Mode(row["mode"]),
    )


def _position_row(row: sqlite3.Row) -> Position:
    return Position(
        account_id=row["account_id"],
        symbol=row["symbol"],
        qty=Decimal(row["qty"]),
        avg_cost=Decimal(row["avg_cost"]),
        mode=Mode(row["mode"]),
    )


def _transaction_row(row: sqlite3.Row) -> Transaction:
    cols = set(row.keys())
    return Transaction(
        id=row["id"],
        account_id=row["account_id"],
        symbol=row["symbol"],
        side=row["side"],
        qty=Decimal(row["qty"]),
        price=Decimal(row["price"]),
        cash_delta=Decimal(row["cash_delta"]),
        realized_pnl=Decimal(row["realized_pnl"]) if row["realized_pnl"] else None,
        created_at=_dt(row["created_at"]),
        mode=Mode(row["mode"]),
        order_id=row["order_id"] if "order_id" in cols else None,
        status=(
            OrderStatus(row["status"])
            if "status" in cols and row["status"]
            else OrderStatus.FILLED
        ),
        simulated=(
            bool(row["simulated"]) if "simulated" in cols else True
        ),
    )


def _order_row(row: sqlite3.Row) -> Order:
    return Order(
        id=row["id"],
        account_id=row["account_id"],
        symbol=row["symbol"],
        side=row["side"],
        qty=Decimal(row["qty"]),
        order_type=row["order_type"] or "market",
        time_in_force=row["time_in_force"] or "day",
        status=OrderStatus(row["status"]),
        filled_qty=Decimal(row["filled_qty"] or "0"),
        avg_fill_price=(
            Decimal(row["avg_fill_price"]) if row["avg_fill_price"] else None
        ),
        provider_order_id=row["provider_order_id"],
        simulated=bool(row["simulated"]),
        idempotency_key=row["idempotency_key"],
        approval_id=row["approval_id"],
        reject_reason=row["reject_reason"],
        mode=Mode(row["mode"]),
        created_at=_dt(row["created_at"]),
        updated_at=_dt(row["updated_at"]),
    )


# ---------------------------------------------------------------- Store


class SqliteStore:
    """Durable ``Store`` protocol implementation on a ``SqliteBackend``."""

    def __init__(self, backend: SqliteBackend) -> None:
        self._b = backend

    # -- accounts ----------------------------------------------------

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

        def write(conn):
            conn.execute(
                "INSERT INTO accounts (id, email, cash, initial_cash,"
                " owner_user_id, mode, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    account.id, account.email, str(account.cash),
                    str(account.initial_cash), account.owner_user_id,
                    account.mode.value, account.created_at.isoformat(),
                ),
            )

        self._b.run(write)
        return account

    def list_accounts_by_owner(self, owner_user_id: str) -> list[Account]:
        def read(conn):
            return [
                _account_row(r)
                for r in conn.execute(
                    "SELECT * FROM accounts WHERE owner_user_id = ?",
                    (owner_user_id,),
                )
            ]

        return self._b.run(read)

    def get_account(self, account_id: str) -> Account | None:
        def read(conn):
            row = conn.execute(
                "SELECT * FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
            return _account_row(row) if row else None

        return self._b.run(read)

    def save_account(self, account: Account) -> None:
        """Write cash mutations back — the object returned by ``get_account``
        is a copy, so in-place edits do not persist on their own."""

        def write(conn):
            conn.execute(
                "UPDATE accounts SET cash = ? WHERE id = ?",
                (str(account.cash), account.id),
            )

        self._b.run(write)

    # -- positions ---------------------------------------------------

    def get_positions(self, account_id: str) -> list[Position]:
        def read(conn):
            return [
                _position_row(r)
                for r in conn.execute(
                    "SELECT * FROM positions WHERE account_id = ?", (account_id,)
                )
            ]

        return self._b.run(read)

    def get_position(self, account_id: str, symbol: str) -> Position | None:
        def read(conn):
            row = conn.execute(
                "SELECT * FROM positions WHERE account_id = ? AND symbol = ?",
                (account_id, symbol),
            ).fetchone()
            return _position_row(row) if row else None

        return self._b.run(read)

    def upsert_position(self, position: Position) -> None:
        def write(conn):
            conn.execute(
                "INSERT INTO positions (account_id, symbol, qty, avg_cost, mode)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(account_id, symbol) DO UPDATE SET"
                " qty=excluded.qty, avg_cost=excluded.avg_cost, mode=excluded.mode",
                (
                    position.account_id, position.symbol, str(position.qty),
                    str(position.avg_cost), position.mode.value,
                ),
            )

        self._b.run(write)

    def remove_position(self, account_id: str, symbol: str) -> None:
        def write(conn):
            conn.execute(
                "DELETE FROM positions WHERE account_id = ? AND symbol = ?",
                (account_id, symbol),
            )

        self._b.run(write)

    # -- transactions ------------------------------------------------

    def add_transaction(self, txn: Transaction) -> None:
        def write(conn):
            conn.execute(
                "INSERT INTO transactions (id, account_id, symbol, side, qty,"
                " price, cash_delta, realized_pnl, mode, order_id, status,"
                " simulated, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    txn.id, txn.account_id, txn.symbol, txn.side, str(txn.qty),
                    str(txn.price), str(txn.cash_delta),
                    str(txn.realized_pnl) if txn.realized_pnl is not None else None,
                    txn.mode.value, txn.order_id, txn.status.value,
                    int(txn.simulated), txn.created_at.isoformat(),
                ),
            )

        self._b.run(write)

    def list_transactions(self, account_id: str) -> list[Transaction]:
        def read(conn):
            return [
                _transaction_row(r)
                for r in conn.execute(
                    "SELECT * FROM transactions WHERE account_id = ?"
                    " ORDER BY created_at",
                    (account_id,),
                )
            ]

        return self._b.run(read)

    # -- snapshots ---------------------------------------------------

    def add_snapshot(self, snapshot: Snapshot) -> None:
        def write(conn):
            conn.execute(
                "INSERT INTO snapshots (id, account_id, total_value, cash, mode,"
                " created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    uuid4().hex[:12], snapshot.account_id,
                    str(snapshot.total_value), str(snapshot.cash),
                    snapshot.mode.value, snapshot.created_at.isoformat(),
                ),
            )

        self._b.run(write)

    def list_snapshots(self, account_id: str) -> list[Snapshot]:
        def read(conn):
            return [
                Snapshot(
                    account_id=r["account_id"],
                    total_value=Decimal(r["total_value"]),
                    cash=Decimal(r["cash"]),
                    created_at=_dt(r["created_at"]),
                    mode=Mode(r["mode"]),
                )
                for r in conn.execute(
                    "SELECT * FROM snapshots WHERE account_id = ?"
                    " ORDER BY created_at",
                    (account_id,),
                )
            ]

        return self._b.run(read)

    # -- goals / plans -----------------------------------------------

    def create_goal(self, text: str, amount: Decimal, account_id: str) -> Goal:
        goal = Goal(
            id=new_id(), text=text, amount=amount, account_id=account_id,
            created_at=utcnow(),
        )

        def write(conn):
            conn.execute(
                "INSERT INTO goals (id, text, amount, account_id, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (goal.id, goal.text, str(goal.amount), goal.account_id,
                 goal.created_at.isoformat()),
            )

        self._b.run(write)
        return goal

    def get_goal(self, goal_id: str) -> Goal | None:
        def read(conn):
            row = conn.execute(
                "SELECT * FROM goals WHERE id = ?", (goal_id,)
            ).fetchone()
            if row is None:
                return None
            return Goal(
                id=row["id"], text=row["text"], amount=Decimal(row["amount"]),
                account_id=row["account_id"], created_at=_dt(row["created_at"]),
            )

        return self._b.run(read)

    def save_plan(self, goal_id: str, plan: dict) -> None:
        def write(conn):
            conn.execute(
                "INSERT INTO plans (goal_id, plan_json) VALUES (?, ?)"
                " ON CONFLICT(goal_id) DO UPDATE SET plan_json=excluded.plan_json",
                (goal_id, json.dumps(plan)),
            )

        self._b.run(write)

    def get_plan(self, goal_id: str) -> dict | None:
        def read(conn):
            row = conn.execute(
                "SELECT plan_json FROM plans WHERE goal_id = ?", (goal_id,)
            ).fetchone()
            return json.loads(row["plan_json"]) if row else None

        return self._b.run(read)

    # -- profiles ----------------------------------------------------

    def get_profile(self, account_id: str) -> UserProfile | None:
        def read(conn):
            row = conn.execute(
                "SELECT * FROM profiles WHERE account_id = ?", (account_id,)
            ).fetchone()
            if row is None:
                return None
            return UserProfile(
                account_id=row["account_id"], risk=row["risk"],
                horizon_years=row["horizon_years"],
                preferences=json.loads(row["preferences_json"]),
                updated_at=_dt(row["updated_at"]),
            )

        return self._b.run(read)

    def save_profile(self, profile: UserProfile) -> UserProfile:
        profile.updated_at = utcnow()

        def write(conn):
            conn.execute(
                "INSERT INTO profiles (account_id, risk, horizon_years,"
                " preferences_json, updated_at) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(account_id) DO UPDATE SET risk=excluded.risk,"
                " horizon_years=excluded.horizon_years,"
                " preferences_json=excluded.preferences_json,"
                " updated_at=excluded.updated_at",
                (
                    profile.account_id, profile.risk, profile.horizon_years,
                    json.dumps(profile.preferences),
                    profile.updated_at.isoformat(),
                ),
            )

        self._b.run(write)
        return profile

    # -- approvals ---------------------------------------------------

    def save_approval(self, request: ApprovalRequest) -> ApprovalRequest:
        def write(conn):
            conn.execute(
                "INSERT INTO approvals (id, account_id, trades_json, total_usd,"
                " status, mode, created_at, decided_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
                " decided_at=excluded.decided_at",
                (
                    request.id, request.account_id, json.dumps(request.trades),
                    str(request.total_usd), request.status, request.mode.value,
                    request.created_at.isoformat(),
                    request.decided_at.isoformat() if request.decided_at else None,
                ),
            )

        self._b.run(write)
        return request

    def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        def read(conn):
            row = conn.execute(
                "SELECT * FROM approvals WHERE id = ?", (approval_id,)
            ).fetchone()
            if row is None:
                return None
            return ApprovalRequest(
                account_id=row["account_id"],
                trades=json.loads(row["trades_json"]),
                total_usd=Decimal(row["total_usd"]),
                status=row["status"],
                id=row["id"],
                created_at=_dt(row["created_at"]),
                decided_at=_dt(row["decided_at"]) if row["decided_at"] else None,
                mode=Mode(row["mode"]),
            )

        return self._b.run(read)

    def list_approvals(
        self, account_id: str, status: str | None = None
    ) -> list[ApprovalRequest]:
        def row_to_approval(row: sqlite3.Row) -> ApprovalRequest:
            return ApprovalRequest(
                account_id=row["account_id"],
                trades=json.loads(row["trades_json"]),
                total_usd=Decimal(row["total_usd"]),
                status=row["status"],
                id=row["id"],
                created_at=_dt(row["created_at"]),
                decided_at=_dt(row["decided_at"]) if row["decided_at"] else None,
                mode=Mode(row["mode"]),
            )

        def read(conn):
            if status is None:
                rows = conn.execute(
                    "SELECT * FROM approvals WHERE account_id = ?",
                    (account_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM approvals WHERE account_id = ? AND status = ?",
                    (account_id, status),
                ).fetchall()
            return [row_to_approval(r) for r in rows]

        return self._b.run(read)


    # -- orders (explicit lifecycle) ---------------------------------

    def save_order(self, order: Order) -> None:
        def write(conn):
            conn.execute(
                "INSERT INTO orders (id, account_id, symbol, side, qty,"
                " order_type, time_in_force, status, filled_qty, avg_fill_price,"
                " provider_order_id, simulated, idempotency_key, approval_id,"
                " reject_reason, mode, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
                " filled_qty=excluded.filled_qty,"
                " avg_fill_price=excluded.avg_fill_price,"
                " provider_order_id=excluded.provider_order_id,"
                " simulated=excluded.simulated,"
                " reject_reason=excluded.reject_reason,"
                " updated_at=excluded.updated_at",
                (
                    order.id, order.account_id, order.symbol, order.side,
                    str(order.qty), order.order_type, order.time_in_force,
                    order.status.value, str(order.filled_qty),
                    str(order.avg_fill_price)
                    if order.avg_fill_price is not None else None,
                    order.provider_order_id, int(order.simulated),
                    order.idempotency_key, order.approval_id,
                    order.reject_reason, order.mode.value,
                    order.created_at.isoformat(), order.updated_at.isoformat(),
                ),
            )

        self._b.run(write)

    def get_order(self, order_id: str) -> Order | None:
        def read(conn):
            row = conn.execute(
                "SELECT * FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
            return _order_row(row) if row else None

        return self._b.run(read)

    def get_order_by_idempotency_key(
        self, account_id: str, key: str
    ) -> Order | None:
        def read(conn):
            row = conn.execute(
                "SELECT * FROM orders WHERE account_id = ?"
                " AND idempotency_key = ?",
                (account_id, key),
            ).fetchone()
            return _order_row(row) if row else None

        return self._b.run(read)

    def list_orders(
        self, account_id: str, status: OrderStatus | None = None
    ) -> list[Order]:
        def read(conn):
            if status is None:
                rows = conn.execute(
                    "SELECT * FROM orders WHERE account_id = ?"
                    " ORDER BY created_at",
                    (account_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM orders WHERE account_id = ? AND status = ?"
                    " ORDER BY created_at",
                    (account_id, status.value),
                ).fetchall()
            return [_order_row(r) for r in rows]

        return self._b.run(read)


# ---------------------------------------------------------------- audit log


class SqliteAuditLog:
    """Durable append-only audit log with the same ``append``/``list``
    contract as :class:`app.governance.audit.AuditLog`."""

    def __init__(self, backend: SqliteBackend) -> None:
        self._b = backend

    def append(
        self,
        *,
        actor: str,
        action: str,
        account_id: str | None = None,
        outcome: str = "success",
        details: dict | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            id=uuid4().hex[:12],
            created_at=datetime.now(UTC),
            actor=actor,
            action=action,
            account_id=account_id,
            outcome=outcome,
            details=dict(details or {}),
        )

        def write(conn):
            conn.execute(
                "INSERT INTO audit_entries (id, created_at, actor, action,"
                " account_id, outcome, details_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.id, entry.created_at.isoformat(), entry.actor,
                    entry.action, entry.account_id, entry.outcome,
                    json.dumps(entry.details),
                ),
            )

        self._b.run(write)
        return entry

    def list(
        self,
        *,
        account_id: str | None = None,
        action: str | None = None,
        limit: int | None = None,
    ) -> list[AuditEntry]:
        def read(conn):
            query = "SELECT * FROM audit_entries WHERE 1=1"
            params: list = []
            if account_id is not None:
                query += " AND account_id = ?"
                params.append(account_id)
            if action is not None:
                query += " AND action = ?"
                params.append(action)
            query += " ORDER BY created_at"
            rows = conn.execute(query, params).fetchall()
            if limit is not None:
                rows = rows[-limit:]
            return [
                AuditEntry(
                    id=r["id"], created_at=_dt(r["created_at"]), actor=r["actor"],
                    action=r["action"], account_id=r["account_id"],
                    outcome=r["outcome"], details=json.loads(r["details_json"]),
                )
                for r in rows
            ]

        return self._b.run(read)


# ---------------------------------------------------------------- event log


class SqliteEventLog:
    """Durable agent event log; same contract as
    :class:`app.agents.events.EventLog`."""

    def __init__(self, backend: SqliteBackend) -> None:
        self._b = backend

    def append(self, agent: str, kind: str, payload: dict | None = None):
        from app.agents.events import AgentEvent

        event = AgentEvent(
            id=uuid4().hex[:12],
            created_at=datetime.now(UTC),
            agent=agent,
            kind=kind,
            payload=dict(payload or {}),
        )

        def write(conn):
            conn.execute(
                "INSERT INTO agent_events (id, created_at, agent, kind, payload_json)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    event.id, event.created_at.isoformat(), event.agent,
                    event.kind, json.dumps(event.payload),
                ),
            )

        self._b.run(write)
        return event

    def list(self, *, agent: str | None = None,
             limit: int | None = None) -> list:
        from app.agents.events import AgentEvent

        def read(conn):
            if agent is None:
                rows = conn.execute(
                    "SELECT * FROM agent_events ORDER BY created_at").fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM agent_events WHERE agent = ? ORDER BY created_at",
                    (agent,)).fetchall()
            if limit is not None:
                rows = rows[-limit:]
            return [
                AgentEvent(
                    id=r["id"], created_at=_dt(r["created_at"]), agent=r["agent"],
                    kind=r["kind"], payload=json.loads(r["payload_json"]),
                )
                for r in rows
            ]

        return self._b.run(read)


# ---------------------------------------------------------------- credits ledger


class SqliteCreditsLedger:
    """Durable credits ledger with the same semantics as
    :class:`app.billing.credits.CreditsLedger`: append-only entries, derived
    balance, idempotent ``credit_unique`` (idempotency survives restarts via
    the ``credit_sessions`` table)."""

    def __init__(self, backend: SqliteBackend) -> None:
        self._b = backend

    def _append(
        self, *, account_id: str, kind: str, credits: int, tool: str,
        meta: dict | None,
    ) -> CreditEntry:
        entry = CreditEntry(
            id=uuid4().hex[:12],
            created_at=datetime.now(UTC),
            account_id=account_id,
            kind=kind,
            credits=credits,
            tool=tool,
            meta=dict(meta or {}),
        )

        def write(conn):
            conn.execute(
                "INSERT INTO credit_entries (id, created_at, account_id, kind,"
                " credits, tool, meta_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.id, entry.created_at.isoformat(), entry.account_id,
                    entry.kind, entry.credits, entry.tool,
                    json.dumps(entry.meta),
                ),
            )

        self._b.run(write)
        return entry

    def credit(self, account_id: str, credits: int, *, tool: str = "stripe",
               meta: dict | None = None) -> CreditEntry:
        if credits <= 0:
            raise ValueError("credit amount must be positive")
        return self._append(account_id=account_id, kind="purchase",
                            credits=credits, tool=tool, meta=meta)

    def credit_unique(self, session_id: str, account_id: str, credits: int, *,
                      tool: str = "stripe",
                      meta: dict | None = None) -> CreditEntry | None:
        if credits <= 0:
            raise ValueError("credit amount must be positive")

        def write(conn):
            cursor = conn.execute(
                "INSERT OR IGNORE INTO credit_sessions (session_id) VALUES (?)",
                (session_id,),
            )
            if cursor.rowcount == 0:
                return None  # replay: session already processed
            entry = CreditEntry(
                id=uuid4().hex[:12],
                created_at=datetime.now(UTC),
                account_id=account_id,
                kind="purchase",
                credits=credits,
                tool=tool,
                meta=dict(meta or {}),
            )
            conn.execute(
                "INSERT INTO credit_entries (id, created_at, account_id, kind,"
                " credits, tool, meta_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.id, entry.created_at.isoformat(), entry.account_id,
                    entry.kind, entry.credits, entry.tool,
                    json.dumps(entry.meta),
                ),
            )
            return entry

        return self._b.run(write)

    def debit(self, account_id: str, credits: int, *, tool: str,
              meta: dict | None = None,
              allow_partial: bool = False) -> tuple[CreditEntry, int]:
        from app.billing.credits import InsufficientCredits

        if credits <= 0:
            raise ValueError("debit amount must be positive")
        balance = self.balance(account_id)
        if balance < credits and not allow_partial:
            raise InsufficientCredits(
                f"account {account_id} has {balance} credits, needs {credits}"
            )
        debited = min(balance, credits)
        shortfall = credits - debited
        entry = self._append(
            account_id=account_id, kind="debit", credits=-debited, tool=tool,
            meta={**(meta or {}), "requested_credits": credits,
                  "shortfall_credits": shortfall},
        )
        return entry, shortfall

    def balance(self, account_id: str) -> int:
        def read(conn):
            row = conn.execute(
                "SELECT COALESCE(SUM(credits), 0) AS total FROM credit_entries"
                " WHERE account_id = ?",
                (account_id,),
            ).fetchone()
            return int(row["total"])

        return self._b.run(read)

    def spent_since(self, account_id: str, since: datetime) -> int:
        def read(conn):
            row = conn.execute(
                "SELECT COALESCE(SUM(-credits), 0) AS spent FROM credit_entries"
                " WHERE account_id = ? AND kind = 'debit' AND created_at >= ?",
                (account_id, since.isoformat()),
            ).fetchone()
            return int(row["spent"])

        return self._b.run(read)

    def list(self, account_id: str, *, kind: str | None = None,
             limit: int | None = None) -> list[CreditEntry]:
        def read(conn):
            if kind is None:
                rows = conn.execute(
                    "SELECT * FROM credit_entries WHERE account_id = ?"
                    " ORDER BY created_at",
                    (account_id,)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM credit_entries WHERE account_id = ?"
                    " AND kind = ? ORDER BY created_at",
                    (account_id, kind)).fetchall()
            if limit is not None:
                rows = rows[-limit:]
            return [
                CreditEntry(
                    id=r["id"], created_at=_dt(r["created_at"]),
                    account_id=r["account_id"], kind=r["kind"],
                    credits=r["credits"], tool=r["tool"],
                    meta=json.loads(r["meta_json"]),
                )
                for r in rows
            ]

        return self._b.run(read)

    def reset(self) -> None:
        def write(conn):
            conn.execute("DELETE FROM credit_entries")
            conn.execute("DELETE FROM credit_sessions")

        self._b.run(write)
