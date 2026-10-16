"""Supabase adapter skeleton for the ``Store`` protocol.

Wired via ``SUPABASE_URL`` / ``SUPABASE_SERVICE_KEY`` (service-role key —
never exposed to the browser). Talks to the Supabase PostgREST API with
httpx.

STATUS: skeleton. The core account/position/transaction/order surface is
implemented and tested against mocked HTTP (no live calls — the real
Supabase project is pending on Roger, so there is nothing live to verify
against). Goals, plans, profiles, and approvals raise
``SupabaseNotImplementedError`` honestly until the project exists and the
table mapping in ``supabase/schema.sql`` is extended for them.

NOTE: table names here (``accounts``/``positions``/``transactions``) are
provisional — ``supabase/schema.sql`` currently names the accounts table
``sandbox_accounts``. The mapping is finalized when Roger's real project
exists; nothing here is presented as the final schema.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

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


class SupabaseConfigError(Exception):
    """Supabase env config is missing."""


class SupabaseNotImplementedError(NotImplementedError):
    """This part of the adapter is not implemented yet (skeleton)."""


class SupabaseRestError(Exception):
    """The Supabase REST API returned an error."""


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class SupabaseStore:
    """``Store`` protocol over Supabase PostgREST. Skeleton: accounts,
    positions, and transactions are implemented; everything else raises
    :class:`SupabaseNotImplementedError`."""

    def __init__(
        self,
        url: str | None = None,
        service_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        url = url or os.environ.get("SUPABASE_URL")
        service_key = service_key or os.environ.get("SUPABASE_SERVICE_KEY")
        if not url or not service_key:
            raise SupabaseConfigError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY are required for the"
                " Supabase store — pending on Roger's Supabase project."
            )
        self._base = url.rstrip("/")
        self._client = httpx.Client(
            base_url=f"{self._base}/rest/v1",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/json",
            },
            transport=transport,
            timeout=10.0,
        )

    # -- low-level ---------------------------------------------------

    def _get(self, table: str, params: dict[str, Any]) -> list[dict]:
        resp = self._client.get(f"/{table}", params=params)
        return self._checked(resp)

    def _post(self, table: str, row: dict) -> dict:
        resp = self._client.post(
            f"/{table}",
            json=row,
            headers={"Prefer": "return=representation"},
        )
        rows = self._checked(resp, expected=(200, 201))
        if not rows:
            raise SupabaseRestError(f"POST /{table} returned no representation")
        return rows[0]

    def _patch(self, table: str, params: dict[str, Any], row: dict) -> None:
        resp = self._client.patch(f"/{table}", params=params, json=row)
        self._checked(resp, expected=(200, 204))

    def _delete(self, table: str, params: dict[str, Any]) -> None:
        resp = self._client.delete(f"/{table}", params=params)
        self._checked(resp, expected=(200, 204))

    @staticmethod
    def _checked(resp: httpx.Response, expected=(200,)) -> list[dict]:
        if resp.status_code not in expected:
            try:
                detail = resp.json()
            except ValueError:
                detail = resp.text
            raise SupabaseRestError(
                f"Supabase REST {resp.status_code}: {detail}"
            )
        if resp.status_code == 204 or not resp.content:
            return []
        return resp.json()

    # -- accounts ----------------------------------------------------

    def create_account(
        self,
        email: str | None,
        initial_cash: Decimal = STARTING_CASH,
        owner_user_id: str = "",
        mode: Mode = Mode.EXPERIMENTAL,
    ) -> Account:
        row = self._post("accounts", {
            "id": new_id(),
            "email": email,
            "cash": str(initial_cash),
            "initial_cash": str(initial_cash),
            "owner_user_id": owner_user_id,
            "mode": mode.value,
            "created_at": utcnow().isoformat(),
        })
        return self._account_row(row)

    def get_account(self, account_id: str) -> Account | None:
        rows = self._get("accounts", {"id": f"eq.{account_id}", "select": "*"})
        return self._account_row(rows[0]) if rows else None

    def list_accounts_by_owner(self, owner_user_id: str) -> list[Account]:
        rows = self._get("accounts", {
            "owner_user_id": f"eq.{owner_user_id}",
            "select": "*",
        })
        return [self._account_row(r) for r in rows]

    def save_account(self, account: Account) -> None:
        self._patch("accounts", {"id": f"eq.{account.id}"},
                    {"cash": str(account.cash)})

    @staticmethod
    def _account_row(row: dict) -> Account:
        return Account(
            id=row["id"],
            email=row.get("email"),
            cash=Decimal(row["cash"]),
            initial_cash=Decimal(row["initial_cash"]),
            created_at=_dt(row.get("created_at")) or utcnow(),
            owner_user_id=row.get("owner_user_id") or "",
            mode=Mode(row.get("mode") or "experimental"),
        )

    # -- positions ---------------------------------------------------

    def get_positions(self, account_id: str) -> list[Position]:
        rows = self._get("positions",
                         {"account_id": f"eq.{account_id}", "select": "*"})
        return [self._position_row(r) for r in rows]

    def get_position(self, account_id: str, symbol: str) -> Position | None:
        rows = self._get("positions", {
            "account_id": f"eq.{account_id}",
            "symbol": f"eq.{symbol}",
            "select": "*",
        })
        return self._position_row(rows[0]) if rows else None

    def upsert_position(self, position: Position) -> None:
        # PostgREST upsert on the (account_id, symbol) primary key.
        resp = self._client.post(
            "/positions",
            json={
                "account_id": position.account_id,
                "symbol": position.symbol,
                "qty": str(position.qty),
                "avg_cost": str(position.avg_cost),
                "mode": position.mode.value,
            },
            headers={"Prefer": "resolution=merge-duplicates"},
        )
        self._checked(resp, expected=(200, 201, 204))

    def remove_position(self, account_id: str, symbol: str) -> None:
        self._delete("positions", {
            "account_id": f"eq.{account_id}", "symbol": f"eq.{symbol}"})

    @staticmethod
    def _position_row(row: dict) -> Position:
        return Position(
            account_id=row["account_id"],
            symbol=row["symbol"],
            qty=Decimal(row["qty"]),
            avg_cost=Decimal(row["avg_cost"]),
            mode=Mode(row.get("mode") or "experimental"),
        )

    # -- transactions ------------------------------------------------

    def add_transaction(self, txn: Transaction) -> None:
        self._post("transactions", {
            "id": txn.id,
            "account_id": txn.account_id,
            "symbol": txn.symbol,
            "side": txn.side,
            "qty": str(txn.qty),
            "price": str(txn.price),
            "cash_delta": str(txn.cash_delta),
            "realized_pnl": (str(txn.realized_pnl)
                             if txn.realized_pnl is not None else None),
            "mode": txn.mode.value,
            "order_id": txn.order_id,
            "status": txn.status.value,
            "simulated": txn.simulated,
            "created_at": txn.created_at.isoformat(),
        })

    def list_transactions(self, account_id: str) -> list[Transaction]:
        rows = self._get("transactions", {
            "account_id": f"eq.{account_id}",
            "select": "*",
            "order": "created_at.asc",
        })
        return [
            Transaction(
                id=r["id"], account_id=r["account_id"], symbol=r["symbol"],
                side=r["side"], qty=Decimal(r["qty"]), price=Decimal(r["price"]),
                cash_delta=Decimal(r["cash_delta"]),
                realized_pnl=(Decimal(r["realized_pnl"])
                              if r.get("realized_pnl") else None),
                created_at=_dt(r.get("created_at")) or utcnow(),
                mode=Mode(r.get("mode") or "experimental"),
                order_id=r.get("order_id"),
                status=OrderStatus(r.get("status") or "filled"),
                simulated=bool(r.get("simulated", True)),
            )
            for r in rows
        ]

    # -- orders (explicit lifecycle) ---------------------------------

    def save_order(self, order: Order) -> None:
        # PostgREST upsert on the id primary key — same pattern as
        # upsert_position. Requires the `orders` table from
        # supabase/schema.sql once Roger's project exists.
        resp = self._client.post(
            "/orders",
            json={
                "id": order.id,
                "account_id": order.account_id,
                "symbol": order.symbol,
                "side": order.side,
                "qty": str(order.qty),
                "order_type": order.order_type,
                "time_in_force": order.time_in_force,
                "status": order.status.value,
                "filled_qty": str(order.filled_qty),
                "avg_fill_price": (
                    str(order.avg_fill_price)
                    if order.avg_fill_price is not None else None
                ),
                "provider_order_id": order.provider_order_id,
                "simulated": order.simulated,
                "idempotency_key": order.idempotency_key,
                "approval_id": order.approval_id,
                "reject_reason": order.reject_reason,
                "mode": order.mode.value,
                "created_at": order.created_at.isoformat(),
                "updated_at": order.updated_at.isoformat(),
            },
            headers={"Prefer": "resolution=merge-duplicates"},
        )
        self._checked(resp, expected=(200, 201, 204))

    @staticmethod
    def _order_row(row: dict) -> Order:
        return Order(
            id=row["id"],
            account_id=row["account_id"],
            symbol=row["symbol"],
            side=row["side"],
            qty=Decimal(row["qty"]),
            order_type=row.get("order_type") or "market",
            time_in_force=row.get("time_in_force") or "day",
            status=OrderStatus(row["status"]),
            filled_qty=Decimal(row.get("filled_qty") or "0"),
            avg_fill_price=(
                Decimal(row["avg_fill_price"])
                if row.get("avg_fill_price") else None
            ),
            provider_order_id=row.get("provider_order_id"),
            simulated=bool(row.get("simulated", True)),
            idempotency_key=row.get("idempotency_key"),
            approval_id=row.get("approval_id"),
            reject_reason=row.get("reject_reason"),
            mode=Mode(row.get("mode") or "experimental"),
            created_at=_dt(row.get("created_at")) or utcnow(),
            updated_at=_dt(row.get("updated_at")) or utcnow(),
        )

    def get_order(self, order_id: str) -> Order | None:
        rows = self._get("orders", {"id": f"eq.{order_id}", "select": "*"})
        return self._order_row(rows[0]) if rows else None

    def get_order_by_idempotency_key(
        self, account_id: str, key: str
    ) -> Order | None:
        rows = self._get("orders", {
            "account_id": f"eq.{account_id}",
            "idempotency_key": f"eq.{key}",
            "select": "*",
        })
        return self._order_row(rows[0]) if rows else None

    def list_orders(
        self, account_id: str, status: OrderStatus | None = None
    ) -> list[Order]:
        params: dict[str, Any] = {
            "account_id": f"eq.{account_id}",
            "select": "*",
            "order": "created_at.asc",
        }
        if status is not None:
            params["status"] = f"eq.{status.value}"
        return [self._order_row(r) for r in self._get("orders", params)]

    # -- everything else: honest skeleton ----------------------------

    def add_snapshot(self, snapshot: Snapshot) -> None:
        raise SupabaseNotImplementedError(
            "snapshots are not mapped to Supabase yet — pending Roger's project")

    def list_snapshots(self, account_id: str) -> list[Snapshot]:
        raise SupabaseNotImplementedError(
            "snapshots are not mapped to Supabase yet — pending Roger's project")

    def create_goal(self, text: str, amount: Decimal, account_id: str) -> Goal:
        raise SupabaseNotImplementedError(
            "goals are not mapped to Supabase yet — pending Roger's project")

    def get_goal(self, goal_id: str) -> Goal | None:
        raise SupabaseNotImplementedError(
            "goals are not mapped to Supabase yet — pending Roger's project")

    def save_plan(self, goal_id: str, plan: dict) -> None:
        raise SupabaseNotImplementedError(
            "plans are not mapped to Supabase yet — pending Roger's project")

    def get_plan(self, goal_id: str) -> dict | None:
        raise SupabaseNotImplementedError(
            "plans are not mapped to Supabase yet — pending Roger's project")

    def get_profile(self, account_id: str) -> UserProfile | None:
        raise SupabaseNotImplementedError(
            "profiles are not mapped to Supabase yet — pending Roger's project")

    def save_profile(self, profile: UserProfile) -> UserProfile:
        raise SupabaseNotImplementedError(
            "profiles are not mapped to Supabase yet — pending Roger's project")

    def save_approval(self, request: ApprovalRequest) -> ApprovalRequest:
        raise SupabaseNotImplementedError(
            "approvals are not mapped to Supabase yet — pending Roger's project")

    def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        raise SupabaseNotImplementedError(
            "approvals are not mapped to Supabase yet — pending Roger's project")

    def list_approvals(
        self, account_id: str, status: str | None = None
    ) -> list[ApprovalRequest]:
        raise SupabaseNotImplementedError(
            "approvals are not mapped to Supabase yet — pending Roger's project")

    def close(self) -> None:
        self._client.close()
