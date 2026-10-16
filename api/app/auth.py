"""API authentication: Supabase JWT (HS256) verification.

- ``SUPABASE_JWT_SECRET`` set   -> Bearer JWT required on account/financial
  endpoints; tokens are verified with HS256 (stdlib hmac, constant-time
  compare). Bad/expired/missing tokens -> 401.
- ``SUPABASE_JWT_SECRET`` unset -> auth DISABLED: a loud startup warning is
  logged and every request runs as the single dev user (``DEV_USER_ID``).
  This matches the web frontend's graceful degradation, and keeps the
  single-user dev path working without headers.

Account ownership: ``require_account_owner`` loads the account and fails
closed — 404 when unknown, 403 when it belongs to another user. In dev
mode, accounts created before ownership existed (blank owner) are claimed
by the single dev user; with auth enabled a blank owner is a 403.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

log = logging.getLogger("finkow.auth")

JWT_SECRET_ENV = "SUPABASE_JWT_SECRET"
DEV_USER_ID = "dev-user"

_bearer = HTTPBearer(auto_error=False)


class AuthError(Exception):
    """A presented credential is invalid (bad signature, expired, malformed)."""


def jwt_secret() -> str | None:
    """The Supabase JWT secret, or None when auth is disabled (dev mode)."""
    return os.environ.get(JWT_SECRET_ENV) or None


def auth_enabled() -> bool:
    return jwt_secret() is not None


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    try:
        return base64.urlsafe_b64decode(segment + padding)
    except (ValueError, binascii.Error) as exc:
        raise AuthError("malformed token encoding") from exc


def verify_supabase_jwt(token: str, secret: str) -> dict:
    """Verify a Supabase access JWT with HS256. Returns the payload dict.

    Raises AuthError on: malformed token, non-HS256 alg (incl. "none"),
    bad signature, missing ``sub``, expired ``exp``.
    """
    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        raise AuthError("malformed token")
    header_b64, payload_b64, signature_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
        signature = _b64url_decode(signature_b64)
    except (AuthError, ValueError) as exc:
        raise AuthError("malformed token") from exc
    if not isinstance(header, dict) or header.get("alg") != "HS256":
        raise AuthError("unsupported token algorithm: only HS256 is accepted")
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{header_b64}.{payload_b64}".encode(),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(signature, expected):
        raise AuthError("invalid token signature")
    if not isinstance(payload, dict) or not payload.get("sub"):
        raise AuthError("token has no subject (sub)")
    exp = payload.get("exp")
    if exp is not None:
        try:
            expired = int(exp) <= int(time.time())
        except (TypeError, ValueError) as exc:
            raise AuthError("token has an invalid exp claim") from exc
        if expired:
            raise AuthError("token is expired")
    return payload


async def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """FastAPI dependency returning the authenticated ``user_id``.

    Dev mode (no secret): returns ``DEV_USER_ID`` without requiring a token.
    Prod mode: requires ``Authorization: Bearer <jwt>``; 401 otherwise.
    """
    secret = jwt_secret()
    if secret is None:
        return DEV_USER_ID
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="authentication required: provide a Supabase JWT as a Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = verify_supabase_jwt(credentials.credentials, secret)
    except AuthError as exc:
        raise HTTPException(
            status_code=401,
            detail=f"invalid credentials: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return str(payload["sub"])


def auth_startup_warning() -> None:
    """Log a loud warning when auth is disabled (dev mode). Call at startup."""
    if not auth_enabled():
        log.warning(
            "================================================================\n"
            "FINKOW AUTH DISABLED — no %s set. Every request runs as the\n"
            "single dev user %r with no token required. Do NOT expose this\n"
            "instance publicly; set %s to enable Supabase JWT auth.\n"
            "================================================================",
            JWT_SECRET_ENV,
            DEV_USER_ID,
            JWT_SECRET_ENV,
        )


def require_account_owner(store, account_id: str, user_id: str):
    """Load an account and enforce ownership. 404 unknown, 403 on mismatch.

    Dev-mode legacy: accounts with a blank owner predate ownership and are
    claimed by the single dev user. With auth enabled, fail closed.
    """
    account = store.get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="account not found")
    owner = getattr(account, "owner_user_id", "") or ""
    if owner == user_id:
        return account
    if owner == "" and not auth_enabled() and user_id == DEV_USER_ID:
        return account
    raise HTTPException(
        status_code=403,
        detail="account does not belong to the authenticated user",
    )
