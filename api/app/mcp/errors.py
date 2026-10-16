"""MCP error contract.

Tool-execution failures are returned as MCP tool results with
``isError: true`` and a JSON payload ``{"code": <int>, "message": <str>}``
in the first content block, so agent clients can branch on machine-readable
codes. The codes mirror JSON-RPC error-code space:

- ``-32xxx``: the MCP-layer contract below (auth, permissions, rate
  limits, mode, not-found, invalid input, backend failures).
- ``-32603``: internal fallback for unexpected failures.

No secrets, stack traces, or internal prompts are ever in the payload.
"""

from __future__ import annotations

AUTH_FAILED = -32001  # unknown/missing API key
PERMISSION_DENIED = -32002  # tool not in the key's permission set
RATE_LIMITED = -32003  # per-key budget exhausted for the window
MODE_REJECTED = -32004  # real mode requested; MCP is experimental-only
NOT_FOUND = -32005  # account / order / approval / symbol not found
INVALID_INPUT = -32006  # argument validation failed
BACKEND_ERROR = -32007  # provider/market/credits failure, real-path refusal
INTERNAL_ERROR = -32603  # unexpected failure (logged server-side)


class McpError(Exception):
    """A tool-layer failure carrying a machine-readable error code."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def payload(self) -> dict:
        return {"code": self.code, "message": self.message}
