"""CORS: the Next.js dev server (http://localhost:3000) calls the API directly
from the browser, so the backend must answer preflights and echo the
frontend origin. Untrusted origins must get no CORS headers."""

from fastapi.testclient import TestClient

from app import main

FRONTEND_ORIGIN = "http://localhost:3000"


def test_preflight_allows_frontend_origin():
    client = TestClient(main.app)
    res = client.options(
        "/api/quotes/AAPL",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.headers.get("access-control-allow-origin") == FRONTEND_ORIGIN


def test_actual_request_echoes_frontend_origin():
    client = TestClient(main.app)
    res = client.get("/api/health", headers={"Origin": FRONTEND_ORIGIN})
    assert res.headers.get("access-control-allow-origin") == FRONTEND_ORIGIN


def test_untrusted_origin_gets_no_cors_headers():
    client = TestClient(main.app)
    res = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in res.headers
