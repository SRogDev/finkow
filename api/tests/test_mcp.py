"""MCP server tests — stdio round-trips, auth boundaries, and the
research → proposal → status workflow.

Unit tests run the tool implementations in-process (memory store, mock
providers — zero live calls). Stdio tests spawn the real server as a
subprocess over JSON-RPC, seeding a SQLite file both processes share.
Mocks are labeled explicitly where they surface.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from app.auth import DEV_USER_ID
from app.main import reset_state
from app.mcp import auth as mcp_auth
from app.mcp import context as mcp_context
from app.mcp import errors as mcp_errors
from app.mcp import tools as mcp_tools
from app.money import to_cash

API_DIR = Path(__file__).resolve().parent.parent

READ_KEY = "test-read-secret-001"
PROPOSE_KEY = "test-propose-secret-002"
KEYS_ENV = f"{READ_KEY}:read,{PROPOSE_KEY}:read+propose"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def mcp_env(monkeypatch):
    """Isolated in-memory MCP context with two configured keys."""
    monkeypatch.setenv("FINKOW_STORE", "memory")
    monkeypatch.setenv("FINKOW_MCP_API_KEYS", KEYS_ENV)
    monkeypatch.delenv("AISA_API_KEY", raising=False)
    reset_state()
    ctx = mcp_context.McpContext.build()
    return ctx


def read_client(ctx) -> mcp_auth.McpClient:
    return ctx.auth.authenticate(READ_KEY)


def propose_client(ctx) -> mcp_auth.McpClient:
    return ctx.auth.authenticate(PROPOSE_KEY)


def seed_account(ctx, cash: str = "10000") -> str:
    store = ctx.store
    account = store.create_account(
        email=None, initial_cash=to_cash(Decimal(cash)), owner_user_id=DEV_USER_ID
    )
    return account.id


# ---------------------------------------------------------------- auth


def test_unknown_key_rejected(mcp_env):
    with pytest.raises(mcp_errors.McpError) as excinfo:
        mcp_env.auth.authenticate("no-such-key")
    assert excinfo.value.code == mcp_errors.AUTH_FAILED


def test_key_permissions_parsed(mcp_env):
    read = read_client(mcp_env)
    propose = propose_client(mcp_env)
    assert read.permissions == frozenset({"read"})
    assert propose.permissions == frozenset({"read", "propose"})
    assert read.key_id != propose.key_id
    # key_id is a fingerprint, never the secret
    assert READ_KEY not in read.key_id


def test_constant_time_compare_used(mcp_env):
    # A wrong-length key must not raise or leak timing info differently —
    # it simply fails authentication.
    with pytest.raises(mcp_errors.McpError):
        mcp_env.auth.authenticate("x")
    with pytest.raises(mcp_errors.McpError):
        mcp_env.auth.authenticate(READ_KEY + "-tampered")


def test_no_keys_configured_rejects_everything(monkeypatch):
    monkeypatch.setenv("FINKOW_STORE", "memory")
    monkeypatch.setenv("FINKOW_MCP_API_KEYS", "")
    reset_state()
    ctx = mcp_context.McpContext.build()
    with pytest.raises(mcp_errors.McpError) as excinfo:
        ctx.auth.authenticate(READ_KEY)
    assert excinfo.value.code == mcp_errors.AUTH_FAILED


# ---------------------------------------------------------------- dispatch boundaries


def test_read_only_key_cannot_propose(mcp_env):
    ctx, client = mcp_env, read_client(mcp_env)
    account_id = seed_account(ctx)
    with pytest.raises(mcp_errors.McpError) as excinfo:
        run(
            mcp_tools.prepare_investment_proposal(
                ctx, client, account_id=account_id,
                allocations=[{"symbol": "AAPL", "weight": "0.5"}],
            )
        )
    assert excinfo.value.code == mcp_errors.PERMISSION_DENIED


def test_rate_limit_rejects_after_budget(mcp_env, monkeypatch):
    monkeypatch.setenv("FINKOW_MCP_RATE_LIMIT_PER_MIN", "2")
    ctx = mcp_context.McpContext.build()  # picks up the tiny budget
    args = {"api_key": READ_KEY, "symbol": "AAPL"}
    run(mcp_context.dispatch(ctx, "get_market_data", args))
    run(mcp_context.dispatch(ctx, "get_market_data", args))
    with pytest.raises(mcp_errors.McpError) as excinfo:
        run(mcp_context.dispatch(ctx, "get_market_data", args))
    assert excinfo.value.code == mcp_errors.RATE_LIMITED


def test_real_mode_rejected(mcp_env):
    ctx, client = mcp_env, read_client(mcp_env)
    with pytest.raises(mcp_errors.McpError) as excinfo:
        run(mcp_tools.get_market_data(ctx, client, symbol="AAPL", mode="real"))
    assert excinfo.value.code == mcp_errors.MODE_REJECTED


def test_every_tool_call_is_audited_without_secrets(mcp_env):
    ctx = mcp_env
    run(mcp_context.dispatch(
        ctx, "get_market_data", {"api_key": READ_KEY, "symbol": "AAPL"}
    ))
    entries = [
        e for e in ctx.audit.list(action="mcp.tool.get_market_data")
    ]
    assert len(entries) == 1
    entry = entries[0]
    assert entry.actor == f"mcp:{read_client(ctx).key_id}"
    assert entry.outcome == "success"
    assert "args_hash" in entry.details
    blob = json.dumps(entry.details)
    assert READ_KEY not in blob
    assert PROPOSE_KEY not in blob


def test_failed_auth_is_audited(mcp_env):
    ctx = mcp_env
    with pytest.raises(mcp_errors.McpError):
        run(mcp_context.dispatch(ctx, "get_market_data",
                                 {"api_key": "bad", "symbol": "AAPL"}))
    entries = ctx.audit.list(action="mcp.tool.get_market_data")
    assert len(entries) == 1
    assert entries[0].outcome == "rejected"
    assert entries[0].actor == "mcp:unknown"


# ---------------------------------------------------------------- read tools


def test_get_portfolio_structured_with_mode_fields(mcp_env):
    ctx, client = mcp_env, read_client(mcp_env)
    account_id = seed_account(ctx)
    out = run(mcp_tools.get_portfolio(ctx, client, account_id=account_id))
    assert out.mode == "experimental"
    assert out.virtual is True
    assert out.account_id == account_id
    assert out.cash == "10000.00"
    assert out.total_value == "10000.00"


def test_get_positions_returns_positions_only(mcp_env):
    ctx, client = mcp_env, read_client(mcp_env)
    account_id = seed_account(ctx)
    out = run(mcp_tools.get_positions(ctx, client, account_id=account_id))
    assert out.mode == "experimental"
    assert out.virtual is True
    assert out.positions == []


def test_get_market_data_mock_labeled(mcp_env):
    ctx, client = mcp_env, read_client(mcp_env)
    out = run(mcp_tools.get_market_data(ctx, client, symbol="AAPL"))
    assert out.symbol == "AAPL"
    assert out.provider == "mock"  # mock universe, labeled — zero live calls
    assert out.mode == "experimental"
    assert out.virtual is True


def test_get_market_data_unknown_symbol(mcp_env):
    ctx = mcp_env
    with pytest.raises(mcp_errors.McpError) as excinfo:
        run(mcp_context.dispatch(
            ctx, "get_market_data",
            {"api_key": READ_KEY, "symbol": "ZZZZ-UNKNOWN"},
        ))
    assert excinfo.value.code == mcp_errors.NOT_FOUND


def test_get_transaction_history(mcp_env):
    ctx, client = mcp_env, read_client(mcp_env)
    account_id = seed_account(ctx)
    out = run(mcp_tools.get_transaction_history(ctx, client, account_id=account_id))
    assert out.mode == "experimental"
    assert out.virtual is True
    assert out.transactions == []


def test_get_portfolio_performance_empty(mcp_env):
    ctx, client = mcp_env, read_client(mcp_env)
    account_id = seed_account(ctx)
    out = run(
        mcp_tools.get_portfolio_performance(ctx, client, account_id=account_id)
    )
    assert out.snapshots == 0
    assert out.mode == "experimental"
    assert out.virtual is True


def test_search_investment_opportunities(mcp_env):
    ctx, client = mcp_env, read_client(mcp_env)
    out = run(
        mcp_tools.search_investment_opportunities(ctx, client, symbols="AAPL,MSFT")
    )
    assert out.mode == "experimental"
    assert len(out.opportunities) >= 1
    assert all(o.symbol in ("AAPL", "MSFT") for o in out.opportunities)


def test_analyze_asset(mcp_env):
    ctx, client = mcp_env, read_client(mcp_env)
    out = run(mcp_tools.analyze_asset(ctx, client, symbol="AAPL"))
    assert out.symbol == "AAPL"
    assert out.verdict in ("healthy", "watch", "risky", "neutral")
    assert out.mode == "experimental"


def test_analyze_portfolio_numbers_only(mcp_env):
    ctx, client = mcp_env, read_client(mcp_env)
    account_id = seed_account(ctx)
    out = run(mcp_tools.analyze_portfolio(ctx, client, account_id=account_id))
    assert out.mode == "experimental"
    assert out.virtual is True
    assert out.total_value == "10000.00"
    assert out.cash_weight == "1.0000"
    assert out.positions_count == 0


def test_get_activity_history(mcp_env):
    ctx, client = mcp_env, read_client(mcp_env)
    out = run(mcp_tools.get_activity_history(ctx, client, limit=5))
    assert out.mode == "experimental"
    assert isinstance(out.events, list)


def test_account_not_found(mcp_env):
    ctx = mcp_env
    with pytest.raises(mcp_errors.McpError) as excinfo:
        run(mcp_context.dispatch(
            ctx, "get_portfolio",
            {"api_key": READ_KEY, "account_id": "nope"},
        ))
    assert excinfo.value.code == mcp_errors.NOT_FOUND


# ---------------------------------------------------------------- propose / validate / status


def test_prepare_proposal_returns_pending_authorization(mcp_env):
    ctx, client = mcp_env, propose_client(mcp_env)
    account_id = seed_account(ctx)
    out = run(
        mcp_tools.prepare_investment_proposal(
            ctx, client, account_id=account_id,
            allocations=[{"symbol": "AAPL", "weight": "0.5"}],
        )
    )
    assert out.status == "pending_authorization"
    assert out.mode == "experimental"
    assert out.virtual is True
    assert len(out.trades) >= 1
    # nothing executed: the account still holds all cash
    store = ctx.store
    assert store.get_account(account_id).cash == to_cash(Decimal("10000"))
    # draft orders exist but none is submitted/filled
    approval = store.get_approval(out.approval_id)
    assert approval.status == "pending"
    for order in ctx.orders.list_for_approval(account_id, out.approval_id):
        assert order.status.value == "draft"
        assert order.simulated is True


def test_prepare_proposal_idempotent_replay(mcp_env):
    ctx, client = mcp_env, propose_client(mcp_env)
    account_id = seed_account(ctx)
    allocations = [{"symbol": "AAPL", "weight": "0.5"}]
    first = run(
        mcp_tools.prepare_investment_proposal(
            ctx, client, account_id=account_id, allocations=allocations,
            idempotency_key="idem-1",
        )
    )
    second = run(
        mcp_tools.prepare_investment_proposal(
            ctx, client, account_id=account_id, allocations=allocations,
            idempotency_key="idem-1",
        )
    )
    assert first.approval_id == second.approval_id
    assert second.idempotent_replay is True
    # no duplicate draft orders were created
    assert len(ctx.orders.list_for_approval(account_id, first.approval_id)) == len(
        first.trades
    )


def test_prepare_proposal_honest_boundary_text(mcp_env):
    ctx, client = mcp_env, propose_client(mcp_env)
    account_id = seed_account(ctx)
    out = run(
        mcp_tools.prepare_investment_proposal(
            ctx, client, account_id=account_id,
            allocations=[{"symbol": "AAPL", "weight": "0.5"}],
        )
    )
    assert "human" in out.requires_approval.lower()
    blob = out.model_dump_json()
    assert "executed" not in blob.lower() or "never" in blob.lower()


def test_validate_investment_action(mcp_env):
    ctx, client = mcp_env, read_client(mcp_env)
    account_id = seed_account(ctx)
    ok = run(
        mcp_tools.validate_investment_action(
            ctx, client, account_id=account_id, symbol="AAPL",
            side="buy", quantity="1",
        )
    )
    assert ok.allowed is True
    denied = run(
        mcp_tools.validate_investment_action(
            ctx, client, account_id=account_id, symbol="AAPL",
            side="buy", quantity="1000000",
        )
    )
    assert denied.allowed is False
    assert any("limit" in r.lower() for r in denied.reasons)


def test_get_order_status_approval_pending(mcp_env):
    ctx, client = mcp_env, propose_client(mcp_env)
    account_id = seed_account(ctx)
    proposal = run(
        mcp_tools.prepare_investment_proposal(
            ctx, client, account_id=account_id,
            allocations=[{"symbol": "AAPL", "weight": "0.5"}],
        )
    )
    out = run(
        mcp_tools.get_order_status(
            ctx, client, approval_id=proposal.approval_id
        )
    )
    assert out.status == "pending_authorization"
    assert out.mode == "experimental"
    assert out.virtual is True
    assert len(out.orders) >= 1
    assert all(o["simulated"] is True for o in out.orders)


def test_get_order_status_requires_one_id(mcp_env):
    ctx, client = mcp_env, read_client(mcp_env)
    with pytest.raises(mcp_errors.McpError) as excinfo:
        run(mcp_tools.get_order_status(ctx, client))
    assert excinfo.value.code == mcp_errors.INVALID_INPUT


def test_research_to_proposal_to_status_workflow(mcp_env):
    """Representative S18 workflow: search → propose → status.

    Mocks explicitly labeled: market data comes from the ``mock`` provider.
    """
    ctx = mcp_env
    reader, proposer = read_client(ctx), propose_client(ctx)
    account_id = seed_account(ctx)

    opps = run(
        mcp_tools.search_investment_opportunities(ctx, reader, symbols="AAPL,MSFT")
    )
    top = opps.opportunities[0].symbol

    proposal = run(
        mcp_tools.prepare_investment_proposal(
            ctx, proposer, account_id=account_id,
            allocations=[{"symbol": top, "weight": "0.4"}],
            idempotency_key="workflow-1",
        )
    )
    assert proposal.status == "pending_authorization"
    assert proposal.virtual is True

    status = run(
        mcp_tools.get_order_status(
            ctx, reader, approval_id=proposal.approval_id
        )
    )
    assert status.status == "pending_authorization"
    assert status.orders, "draft orders must be visible on the pending approval"
    # the proposal moved nothing: still all cash
    assert ctx.store.get_account(account_id).cash == to_cash(Decimal("10000"))


def test_no_secrets_in_tool_outputs(mcp_env):
    ctx, client = mcp_env, read_client(mcp_env)
    account_id = seed_account(ctx)
    outputs = [
        run(mcp_tools.get_portfolio(ctx, client, account_id=account_id)),
        run(mcp_tools.get_market_data(ctx, client, symbol="AAPL")),
        run(mcp_tools.get_activity_history(ctx, client)),
    ]
    for out in outputs:
        blob = out.model_dump_json()
        assert READ_KEY not in blob
        assert PROPOSE_KEY not in blob


# ---------------------------------------------------------------- stdio round-trips


class StdioClient:
    """Minimal JSON-RPC-over-stdio client for spawning the real server."""

    def __init__(self, proc: subprocess.Popen):
        self._proc = proc
        self._next_id = 0

    def _send(self, method: str, params: dict | None = None, notif: bool = False):
        self._next_id += 1
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if not notif:
            msg["id"] = self._next_id
        if params is not None:
            msg["params"] = params
        self._proc.stdin.write((json.dumps(msg) + "\n").encode())
        self._proc.stdin.flush()
        if notif:
            return None
        line = self._proc.stdout.readline()
        assert line, "server closed stdout unexpectedly"
        return json.loads(line)

    def initialize(self):
        resp = self._send(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "mcp-test", "version": "0.1"},
            },
        )
        assert "result" in resp, resp
        self._send("notifications/initialized", notif=True)
        return resp["result"]

    def list_tools(self):
        resp = self._send("tools/list")
        assert "result" in resp, resp
        return resp["result"]["tools"]

    def call(self, name: str, arguments: dict):
        resp = self._send("tools/call", {"name": name, "arguments": arguments})
        assert "result" in resp, resp
        return resp["result"]

    def call_error(self, name: str, arguments: dict) -> dict:
        """Call a tool expected to fail; return the parsed error payload.

        The SDK prefixes ToolError text with 'Error executing tool <name>: ';
        the JSON {"code", "message"} payload follows the prefix.
        """
        result = self.call(name, arguments)
        assert result["isError"] is True, result
        text = result["content"][0]["text"]
        return json.loads(text[text.index("{"):])


@pytest.fixture()
def stdio_server(tmp_path, monkeypatch):
    """Spawn the real MCP server; seed a shared SQLite store first."""
    db_path = tmp_path / "mcp-test.db"
    env = {
        **os.environ,
        "PATH": os.environ["PATH"],
        "FINKOW_STORE": "sqlite",
        "FINKOW_DB_PATH": str(db_path),
        "FINKOW_MCP_API_KEYS": KEYS_ENV,
    }
    monkeypatch.setenv("FINKOW_DB_PATH", str(db_path))
    # Seed through the same SQLite backend the child process will open.
    from app.main import build_storage

    store, _, _ = build_storage("sqlite")
    account = store.create_account(
        email=None, initial_cash=to_cash(Decimal("10000")),
        owner_user_id=DEV_USER_ID,
    )
    account_id = account.id

    uv_bin = str(Path.home() / ".local" / "bin" / "uv")
    proc = subprocess.Popen(
        [uv_bin, "run", "python", "-m", "app.mcp.server"],
        cwd=str(API_DIR),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    client = StdioClient(proc)
    try:
        client.initialize()
        yield client, account_id
    finally:
        proc.stdin.close()
        proc.wait(timeout=15)


EXPECTED_TOOLS = [
    "get_portfolio",
    "get_positions",
    "get_transaction_history",
    "get_portfolio_performance",
    "get_market_data",
    "search_investment_opportunities",
    "analyze_asset",
    "analyze_portfolio",
    "get_activity_history",
    "prepare_investment_proposal",
    "validate_investment_action",
    "get_order_status",
]


def test_stdio_lists_all_twelve_tools(stdio_server):
    client, _ = stdio_server
    tools = client.list_tools()
    names = [t["name"] for t in tools]
    assert names == EXPECTED_TOOLS
    for tool in tools:
        assert "api_key" in tool["inputSchema"]["properties"]
        assert "api_key" in tool["inputSchema"]["required"]
        assert "outputSchema" in tool


def test_stdio_read_tools_structured_output(stdio_server):
    client, account_id = stdio_server
    args = {"api_key": READ_KEY, "account_id": account_id, "mode": "experimental"}
    for name in [
        "get_portfolio", "get_positions", "get_transaction_history",
        "get_portfolio_performance", "analyze_portfolio",
    ]:
        result = client.call(name, args)
        assert result["isError"] is False, (name, result)
        payload = result["structuredContent"]
        assert payload["mode"] == "experimental", name
        assert payload["virtual"] is True, name


def test_stdio_market_and_research_tools(stdio_server):
    client, _ = stdio_server
    key = {"api_key": READ_KEY, "mode": "experimental"}
    quote = client.call("get_market_data", {**key, "symbol": "AAPL"})
    assert quote["isError"] is False
    assert quote["structuredContent"]["symbol"] == "AAPL"
    assert quote["structuredContent"]["provider"] == "mock"

    opps = client.call(
        "search_investment_opportunities", {**key, "symbols": "AAPL,MSFT"}
    )
    assert opps["isError"] is False
    assert len(opps["structuredContent"]["opportunities"]) >= 1

    analysis = client.call("analyze_asset", {**key, "symbol": "AAPL"})
    assert analysis["isError"] is False
    assert analysis["structuredContent"]["symbol"] == "AAPL"

    activity = client.call("get_activity_history", {**key, "limit": 5})
    assert activity["isError"] is False
    assert isinstance(activity["structuredContent"]["events"], list)


def test_stdio_validate_and_status_tools(stdio_server):
    client, account_id = stdio_server
    key = {"api_key": READ_KEY, "account_id": account_id, "mode": "experimental"}
    valid = client.call(
        "validate_investment_action",
        {**key, "symbol": "AAPL", "side": "buy", "quantity": "1"},
    )
    assert valid["isError"] is False
    assert valid["structuredContent"]["allowed"] is True

    missing = client.call("get_order_status", {"api_key": READ_KEY})
    assert missing["isError"] is True
    err = client.call_error("get_order_status", {"api_key": READ_KEY})
    assert err["code"] == mcp_errors.INVALID_INPUT


def test_stdio_propose_workflow_pending_authorization(stdio_server):
    client, account_id = stdio_server
    key = {"api_key": PROPOSE_KEY, "account_id": account_id, "mode": "experimental"}
    proposal = client.call(
        "prepare_investment_proposal",
        {**key, "allocations": [{"symbol": "AAPL", "weight": "0.4"}],
         "idempotency_key": "stdio-workflow-1"},
    )
    assert proposal["isError"] is False
    payload = proposal["structuredContent"]
    assert payload["status"] == "pending_authorization"
    assert payload["virtual"] is True

    status = client.call(
        "get_order_status",
        {"api_key": READ_KEY, "approval_id": payload["approval_id"],
         "mode": "experimental"},
    )
    assert status["isError"] is False
    assert status["structuredContent"]["status"] == "pending_authorization"


def test_stdio_bad_key_rejected(stdio_server):
    client, account_id = stdio_server
    err = client.call_error(
        "get_portfolio",
        {"api_key": "wrong-key", "account_id": account_id},
    )
    assert err["code"] == mcp_errors.AUTH_FAILED


def test_stdio_read_key_cannot_propose(stdio_server):
    client, account_id = stdio_server
    err = client.call_error(
        "prepare_investment_proposal",
        {"api_key": READ_KEY, "account_id": account_id,
         "allocations": [{"symbol": "AAPL", "weight": "0.4"}]},
    )
    assert err["code"] == mcp_errors.PERMISSION_DENIED


def test_stdio_real_mode_rejected(stdio_server):
    client, _ = stdio_server
    err = client.call_error(
        "get_market_data",
        {"api_key": READ_KEY, "symbol": "AAPL", "mode": "real"},
    )
    assert err["code"] == mcp_errors.MODE_REJECTED
