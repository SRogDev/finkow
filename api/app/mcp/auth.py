"""MCP client authentication: static API keys with permission sets.

``FINKOW_MCP_API_KEYS`` is a comma-separated list of entries. Each entry is

    <secret>[:<perms>[:<user_id>]]

- ``<secret>``: the key the client presents (compared in constant time).
- ``<perms>``: ``read`` (default) or ``read+propose``. ``read`` covers all
  read-only tools; ``read+propose`` additionally allows
  ``prepare_investment_proposal``. No other permission exists.
- ``<user_id>``: the user the key acts on behalf of. Account ownership is
  enforced against this user exactly as in the REST app. Defaults to the
  dev user; operators must bind real user ids in production.

An agent must not grant itself permissions — keys and their permission
sets are operator configuration only. Unknown keys are rejected; when no
keys are configured, every call is rejected (safe by default).
"""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass

from app.auth import DEV_USER_ID
from app.mcp.errors import AUTH_FAILED, McpError

ENV_VAR = "FINKOW_MCP_API_KEYS"

PERM_READ = "read"
PERM_PROPOSE = "propose"
KNOWN_PERMS = {PERM_READ, PERM_PROPOSE}


@dataclass(frozen=True)
class McpClient:
    """An authenticated MCP client.

    ``key_id`` is a sha256 fingerprint — the secret itself is never stored
    on the client record, never logged, and never returned to callers.
    """

    key_id: str
    permissions: frozenset[str]
    user_id: str

    def can(self, permission: str) -> bool:
        return permission in self.permissions


class McpAuth:
    """Parses ``FINKOW_MCP_API_KEYS`` and authenticates presented secrets."""

    def __init__(self, raw: str | None = None) -> None:
        self._secrets: list[tuple[str, McpClient]] = []
        source = os.environ.get(ENV_VAR, "") if raw is None else raw
        for entry in source.split(","):
            parsed = self._parse_entry(entry.strip())
            if parsed is not None:
                self._secrets.append(parsed)

    @staticmethod
    def _parse_entry(entry: str) -> tuple[str, McpClient] | None:
        if not entry:
            return None
        parts = entry.split(":")
        secret = parts[0].strip()
        if not secret:
            return None
        perms_raw = parts[1].strip() if len(parts) > 1 and parts[1].strip() else PERM_READ
        user_id = (
            parts[2].strip()
            if len(parts) > 2 and parts[2].strip()
            else DEV_USER_ID
        )
        perms = frozenset(p.strip() for p in perms_raw.split("+") if p.strip())
        if not perms.issubset(KNOWN_PERMS):
            raise ValueError(
                f"unknown permission in {ENV_VAR} entry: {perms_raw!r} "
                f"(expected 'read' or 'read+propose')"
            )
        key_id = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]
        return secret, McpClient(key_id=key_id, permissions=perms, user_id=user_id)

    def authenticate(self, presented: str) -> McpClient:
        """Return the client for ``presented`` or raise AUTH_FAILED.

        Comparison is constant-time; an unknown key fails closed with no
        information about configured keys.
        """
        if not presented:
            raise McpError(AUTH_FAILED, "missing api_key: MCP authentication required")
        for secret, client in self._secrets:
            if hmac.compare_digest(presented, secret):
                return client
        raise McpError(AUTH_FAILED, "invalid api_key: MCP authentication rejected")
