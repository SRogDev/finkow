"""API auth: Supabase JWT (HS256) verification + dev-mode degradation.

- Secret set   -> Bearer JWT required, verified with HS256; bad tokens -> 401.
- Secret unset -> auth DISABLED, loud startup warning, single dev user.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import time

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.auth import (
    DEV_USER_ID,
    AuthError,
    auth_enabled,
    auth_startup_warning,
    require_user,
    verify_supabase_jwt,
)

TEST_SECRET = "test-supabase-jwt-secret-0123456789abcdef"


def forge_jwt(payload: dict, secret: str = TEST_SECRET) -> str:
    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = b64(json.dumps(payload).encode())
    sig = b64(hmac.new(secret.encode(), f"{header}.{body}".encode(),
                       hashlib.sha256).digest())
    return f"{header}.{body}.{sig}"


def creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_verify_valid_token():
    payload = {"sub": "user-123", "exp": int(time.time()) + 3600}
    out = verify_supabase_jwt(forge_jwt(payload), TEST_SECRET)
    assert out["sub"] == "user-123"


def test_verify_wrong_signature():
    payload = {"sub": "user-123", "exp": int(time.time()) + 3600}
    with pytest.raises(AuthError):
        verify_supabase_jwt(forge_jwt(payload, secret="wrong-secret"), TEST_SECRET)


def test_verify_expired_token():
    payload = {"sub": "user-123", "exp": int(time.time()) - 10}
    with pytest.raises(AuthError):
        verify_supabase_jwt(forge_jwt(payload), TEST_SECRET)


def test_verify_rejects_none_alg():
    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = b64(json.dumps({"alg": "none"}).encode())
    body = b64(json.dumps({"sub": "user-123"}).encode())
    with pytest.raises(AuthError):
        verify_supabase_jwt(f"{header}.{body}.", TEST_SECRET)


def test_verify_rejects_missing_sub():
    payload = {"exp": int(time.time()) + 3600}
    with pytest.raises(AuthError):
        verify_supabase_jwt(forge_jwt(payload), TEST_SECRET)


def test_verify_rejects_malformed():
    with pytest.raises(AuthError):
        verify_supabase_jwt("not-a-jwt", TEST_SECRET)


def test_require_user_dev_mode_needs_no_token(monkeypatch):
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    assert not auth_enabled()
    assert asyncio.run(require_user(None)) == DEV_USER_ID


def test_require_user_valid_token(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_SECRET)
    assert auth_enabled()
    token = forge_jwt({"sub": "user-abc", "exp": int(time.time()) + 3600})
    assert asyncio.run(require_user(creds(token))) == "user-abc"


def test_require_user_missing_token_is_401(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_SECRET)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_user(None))
    assert exc.value.status_code == 401


def test_require_user_bad_token_is_401(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_SECRET)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_user(creds("bogus.token.here")))
    assert exc.value.status_code == 401


def test_require_user_expired_token_is_401(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_SECRET)
    token = forge_jwt({"sub": "user-abc", "exp": int(time.time()) - 5})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_user(creds(token)))
    assert exc.value.status_code == 401


def test_startup_warning_when_disabled(monkeypatch, caplog):
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    with caplog.at_level("WARNING"):
        auth_startup_warning()
    assert any("auth" in r.message.lower() and "disabled" in r.message.lower()
               for r in caplog.records)


def test_no_warning_when_enabled(monkeypatch, caplog):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_SECRET)
    with caplog.at_level("WARNING"):
        auth_startup_warning()
    assert not any("disabled" in r.message.lower() for r in caplog.records)
