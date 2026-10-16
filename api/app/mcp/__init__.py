"""Finkow MCP server: first-class MCP access to implemented capabilities.

The MCP surface exposes ONLY what the backend actually implements, reusing
the domain modules directly (portfolio valuation, the opportunity hunter,
the analyst, the executor's propose path) — no second financial domain,
no parallel accounting.

Transport: MCP stdio (JSON-RPC 2.0) via the official ``mcp`` Python SDK.
Authentication: per-call ``api_key`` argument (stdio has no headers),
validated against ``FINKOW_MCP_API_KEYS`` with constant-time comparison.

Mode: experimental only. Every response carries ``mode`` and ``virtual``
labels; real-mode requests are rejected — real execution does not exist
in this build (``LiveTradingDisabledError`` by design).

Permissions: ``read`` (all read tools) and ``read+propose``
(``prepare_investment_proposal``). There is deliberately NO execution tool:
``prepare_investment_proposal`` goes through the executor's dry-run propose
path, creates DRAFT orders, and returns ``status: "pending_authorization"``.
Only the human confirmation gate (in-app) can move money.
"""

from __future__ import annotations
