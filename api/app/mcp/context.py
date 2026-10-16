"""MCP request context and the central dispatch gate.

``McpContext.build()`` wires the server from the existing backend modules
(the same store, market port, LLM, events, and audit log the REST app
uses) — the MCP surface adds authentication, permissions, rate limits,
and audit logging around them, not a second domain.

``dispatch(ctx, tool_name, args)`` is the single choke point every tool
call passes through: authenticate → rate limit → permission → mode →
execute → audit. ``server.py`` only adapts this to the MCP SDK.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os

from fastapi import HTTPException

from app.agents.events import EventLog
from app.agents.executor import InvestmentExecutor
from app.agents.radar import OpportunityRadar
from app.auth import require_account_owner
from app.brokerage import LiveTradingDisabledError
from app.governance.audit import AuditLog
from app.governance.metering import CreditsExhausted
from app.governance.rate_limiter import RateLimiter
from app.harness.orchestrator import Orchestrator
from app.market import SymbolNotFound
from app.mcp import auth as mcp_auth
from app.mcp import errors as mcp_errors
from app.modes import Mode, coerce_mode
from app.orders import OrderLifecycle

log = logging.getLogger("finkow.mcp")

RATE_LIMIT_ENV = "FINKOW_MCP_RATE_LIMIT_PER_MIN"
DEFAULT_RATE_LIMIT_PER_MIN = 60

PERM_READ = mcp_auth.PERM_READ
PERM_PROPOSE = mcp_auth.PERM_PROPOSE


def _primary_market_port():
    """The same primary market-data provider the human app uses (AIsa when
    keyed, the deterministic mock otherwise) WITHOUT the free live fallback
    chain. On the MCP path an unknown symbol is a clean NOT_FOUND instead
    of a surprise external call; the ``provider`` field in every quote names
    the source honestly.
    """
    from app.providers import _aisa_key, _metered
    from app.providers.aisa import AisaMarketData
    from app.providers.mock import MockMarketData

    key = _aisa_key()
    if key:
        return _metered(AisaMarketData(key), "aisa.market", "market")
    return MockMarketData()


class McpContext:
    """All shared state for the MCP server process."""

    def __init__(
        self,
        *,
        store,
        market,
        llm,
        search,
        events: EventLog,
        audit: AuditLog,
        auth: mcp_auth.McpAuth,
        rate_limiter: RateLimiter,
    ) -> None:
        self.store = store
        self.market = market
        self.llm = llm
        self.search = search
        self.events = events
        self.audit = audit
        self.auth = auth
        self.rate_limiter = rate_limiter
        self.executor = InvestmentExecutor(store, market, events, audit)
        self.orders = OrderLifecycle(store)
        self.orchestrator = Orchestrator(
            store=store, market=market, llm=llm, search=search,
            events=events, audit=audit,
        )
        self.radar = OpportunityRadar(market, llm, events)
        # Idempotency keys for prepare_investment_proposal (process-local;
        # the store-level order idempotency keys remain on draft orders).
        self.idempotency: dict[str, str] = {}

    @classmethod
    def build(cls) -> McpContext:
        # Imported here so tests can reset app.main's globals before wiring.
        from app import main as app_main

        return cls(
            store=app_main.get_store(),
            market=_primary_market_port(),
            llm=app_main.get_llm(),
            search=app_main.get_search(),
            events=app_main.get_events(),
            audit=app_main.get_audit(),
            auth=mcp_auth.McpAuth(),
            rate_limiter=RateLimiter(
                max_calls=int(os.environ.get(RATE_LIMIT_ENV, "") or DEFAULT_RATE_LIMIT_PER_MIN),
                window_seconds=60.0,
            ),
        )

    def audit_call(
        self,
        *,
        client: mcp_auth.McpClient | None,
        tool: str,
        outcome: str,
        args: dict,
        account_id: str | None = None,
        note: str | None = None,
    ) -> None:
        """Audit every tool call. Only an args hash is stored — never the
        API key and never raw client arguments."""
        safe_args = {k: v for k, v in args.items() if k != "api_key"}
        args_hash = hashlib.sha256(
            json.dumps(safe_args, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]
        details: dict = {"tool": tool, "args_hash": args_hash}
        if note:
            details["note"] = note
        self.audit.append(
            actor=f"mcp:{client.key_id}" if client else "mcp:unknown",
            action=f"mcp.tool.{tool}",
            account_id=account_id,
            outcome=outcome,
            details=details,
        )


def _map_exception(exc: BaseException) -> mcp_errors.McpError:
    if isinstance(exc, mcp_errors.McpError):
        return exc
    if isinstance(exc, HTTPException):
        code = {
            401: mcp_errors.AUTH_FAILED,
            403: mcp_errors.PERMISSION_DENIED,
            404: mcp_errors.NOT_FOUND,
            400: mcp_errors.INVALID_INPUT,
        }.get(exc.status_code, mcp_errors.BACKEND_ERROR)
        detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail)
        return mcp_errors.McpError(code, detail)
    if isinstance(exc, SymbolNotFound):
        return mcp_errors.McpError(mcp_errors.NOT_FOUND, str(exc))
    if isinstance(exc, LiveTradingDisabledError):
        return mcp_errors.McpError(mcp_errors.BACKEND_ERROR, str(exc))
    if isinstance(exc, CreditsExhausted):
        return mcp_errors.McpError(
            mcp_errors.BACKEND_ERROR,
            "credits exhausted: agents cannot make paid provider calls",
        )
    if isinstance(exc, ValueError):
        return mcp_errors.McpError(mcp_errors.INVALID_INPUT, str(exc))
    log.exception("unexpected MCP tool failure")
    return mcp_errors.McpError(
        mcp_errors.INTERNAL_ERROR, "internal error processing the tool call"
    )


def require_experimental(mode: str) -> Mode:
    """MCP is experimental-only: real-mode requests are rejected outright."""
    try:
        parsed = coerce_mode(mode)
    except ValueError as exc:
        raise mcp_errors.McpError(mcp_errors.INVALID_INPUT, str(exc)) from exc
    if parsed is Mode.REAL:
        raise mcp_errors.McpError(
            mcp_errors.MODE_REJECTED,
            "real mode is not exposed over MCP: only experimental (virtual) "
            "state is available, and real execution does not exist in this "
            "build.",
        )
    return parsed


async def dispatch(ctx: McpContext, tool_name: str, args: dict):
    """Authenticate → rate limit → permission → mode → execute → audit.

    Raises McpError; callers translate it to the transport's error shape.
    """
    from app.mcp import tools as mcp_tools

    impl = mcp_tools.TOOLS.get(tool_name)
    if impl is None:
        raise mcp_errors.McpError(
            mcp_errors.INVALID_INPUT, f"unknown tool: {tool_name}"
        )
    required_perm, func = impl
    args = dict(args or {})
    api_key = args.get("api_key")

    client: mcp_auth.McpClient | None = None
    try:
        client = ctx.auth.authenticate(api_key or "")
        rate_key = f"mcp:{client.key_id}"
        if not ctx.rate_limiter.acquire(rate_key):
            raise mcp_errors.McpError(
                mcp_errors.RATE_LIMITED,
                "MCP rate limit exceeded for this API key; retry after the window",
            )
        if not client.can(required_perm):
            raise mcp_errors.McpError(
                mcp_errors.PERMISSION_DENIED,
                f"tool '{tool_name}' requires '{required_perm}' permission; "
                "this API key is read-only. Permissions are operator "
                "configuration — an agent cannot grant itself permissions.",
            )
        mode = require_experimental(str(args.get("mode", "experimental")))
        call_args = {
            k: v for k, v in args.items() if k not in ("api_key", "mode")
        }
        result = await func(ctx, client, mode=mode, **call_args)
    except BaseException as exc:
        err = _map_exception(exc)
        outcome = (
            "rejected"
            if err.code
            in (
                mcp_errors.AUTH_FAILED,
                mcp_errors.PERMISSION_DENIED,
                mcp_errors.RATE_LIMITED,
                mcp_errors.MODE_REJECTED,
            )
            else "failed"
        )
        ctx.audit_call(
            client=client, tool=tool_name, outcome=outcome, args=args,
            note=err.message,
        )
        raise err from exc
    ctx.audit_call(client=client, tool=tool_name, outcome="success", args=args)
    return result


def account_for(ctx: McpContext, client: mcp_auth.McpClient, account_id: str):
    """Load an account enforcing ownership — same rule as the REST app."""
    return require_account_owner(ctx.store, account_id, client.user_id)
