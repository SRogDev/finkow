"""API flow: signup -> $100k -> quote -> buy AAPL + BTC -> portfolio -> AI explain."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import main
from app.market import Quote


class FakeMarket:
    """Deterministic quotes; prices mutable to simulate market movement."""

    def __init__(self):
        self.prices = {"AAPL": Decimal("150.00"), "BTC": Decimal("60000.00")}

    async def get_quote(self, symbol: str) -> Quote:
        sym = symbol.upper()
        if sym not in self.prices:
            from app.market import SymbolNotFound

            raise SymbolNotFound(sym)
        return Quote(
            symbol=sym,
            price=self.prices[sym],
            currency="USD",
            as_of=datetime.now(UTC),
            provider="fake",
        )


@pytest.fixture()
def client():
    c = make_test_client()
    yield c
    main.app.dependency_overrides.clear()


def make_test_client():
    main.reset_state()  # fresh in-memory store per test
    fake = FakeMarket()
    main.app.dependency_overrides[main.get_market] = lambda: fake
    c = TestClient(main.app)
    c.fake_market = fake  # type: ignore[attr-defined]
    return c


def test_signup_grants_100k_virtual():
    resp = make_test_client().post("/api/accounts", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["cash"] == "100000.00"
    assert body["initial_cash"] == "100000.00"
    assert body["account_id"]


def test_full_buy_hold_sell_flow(client):
    c = client
    account_id = c.post("/api/accounts", json={}).json()["account_id"]

    # real-shaped quote
    q = c.get("/api/quotes/AAPL").json()
    assert Decimal(q["price"]) == Decimal("150.00") and q["stale"] is False

    # buy 10 AAPL @ 150 -> cash 98500
    buy = c.post(
        "/api/orders",
        json={"account_id": account_id, "symbol": "AAPL", "side": "buy", "quantity": "10"},
    ).json()
    assert buy["cash_after"] == "98500.00"

    # buy 0.5 BTC @ 60000 -> cash 68500
    c.post(
        "/api/orders",
        json={"account_id": account_id, "symbol": "BTC", "side": "buy", "quantity": "0.5"},
    )
    pf = c.get(f"/api/accounts/{account_id}/portfolio").json()
    assert pf["cash"] == "68500.00"
    assert pf["total_value"] == "100000.00"
    assert pf["total_return_pct"] == "0.00"
    alloc = pf["allocation"]
    assert alloc["BTC"] == "0.3000"
    assert alloc["CASH"] == "0.6850"

    # market moves: BTC -> 66000. Portfolio gains $3000.
    c.fake_market.prices["BTC"] = Decimal("66000.00")
    pf2 = c.get(f"/api/accounts/{account_id}/portfolio").json()
    assert pf2["total_value"] == "103000.00"
    assert pf2["total_return_pct"] == "3.00"
    btc = next(p for p in pf2["positions"] if p["symbol"] == "BTC")
    assert btc["unrealized_pnl"] == "3000.00"

    # sell 5 AAPL @ 150 -> realized pnl 0, cash 69250
    sell = c.post(
        "/api/orders",
        json={"account_id": account_id, "symbol": "AAPL", "side": "sell", "quantity": "5"},
    ).json()
    assert sell["realized_pnl"] == "0.00"
    assert sell["cash_after"] == "69250.00"

    # ledger + history exist
    txns = c.get(f"/api/accounts/{account_id}/transactions").json()["transactions"]
    assert len(txns) == 3
    assert [t["side"] for t in txns] == ["buy", "buy", "sell"]
    hist = c.get(f"/api/accounts/{account_id}/history").json()["snapshots"]
    assert len(hist) >= 3
    assert hist[-1]["total_value"] == "103000.00"


def test_cannot_overspend(client):
    c = client
    account_id = c.post("/api/accounts", json={}).json()["account_id"]
    resp = c.post(
        "/api/orders",
        json={"account_id": account_id, "symbol": "BTC", "side": "buy", "quantity": "100"},
    )
    assert resp.status_code == 400
    assert "insufficient" in resp.json()["detail"].lower()


def test_cannot_oversell(client):
    c = client
    account_id = c.post("/api/accounts", json={}).json()["account_id"]
    c.post(
        "/api/orders",
        json={"account_id": account_id, "symbol": "AAPL", "side": "buy", "quantity": "1"},
    )
    resp = c.post(
        "/api/orders",
        json={"account_id": account_id, "symbol": "AAPL", "side": "sell", "quantity": "2"},
    )
    assert resp.status_code == 400


def test_unknown_symbol_quote_404(client):
    assert client.get("/api/quotes/NOPEXYZ").status_code == 404


def test_ai_explain_is_grounded_in_portfolio(client):
    c = client
    account_id = c.post("/api/accounts", json={}).json()["account_id"]
    c.post(
        "/api/orders",
        json={"account_id": account_id, "symbol": "BTC", "side": "buy", "quantity": "0.5"},
    )
    c.fake_market.prices["BTC"] = Decimal("66000.00")
    resp = c.post(
        "/api/ai/explain",
        json={"account_id": account_id, "question": "what happened to my portfolio?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["grounded"] is True
    # answer must reference real computed numbers, not hallucinations
    assert "103000" in body["answer"].replace(",", "")
    assert "BTC" in body["answer"]
