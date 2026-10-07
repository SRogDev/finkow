"""Agent money layer, part 3: simulated end-to-end investment flow with credits.

Full loop: Stripe webhook grants credits -> orchestrator invest flow debits the
mocked AIsa costs -> balance exact -> tiny cap blocks the next paid call.
"""

import asyncio
import sys
import types

import pytest
from fastapi.testclient import TestClient

from app import main
from app.providers.mock import MockLLM, MockMarketData, MockWebSearch


def _run(coro):
    return asyncio.run(coro)


class PaidMockMarketData(MockMarketData):
    name = "paid-mock"
    last_cost_micros_usd = 20000  # $0.02 per call


class PaidMockLLM(MockLLM):
    name = "paid-mock"
    last_cost_micros_usd = 5000  # $0.005 per call


class PaidMockSearch(MockWebSearch):
    name = "paid-mock"
    last_cost_micros_usd = 16000  # $0.016 per call


def _install_fake_stripe(monkeypatch, event=None):
    fake = types.ModuleType("stripe")
    calls = []
    state = {"event": event}

    class FakeSession:
        @staticmethod
        def create(**kwargs):
            calls.append(("Session.create", kwargs))
            return {"id": "cs_test_credits_1", "url": "https://checkout.stripe.test/pay/c1"}

    class FakeCheckout:
        Session = FakeSession

    class FakeWebhook:
        @staticmethod
        def construct_event(payload, signature, secret):
            if signature != "valid-sig":
                raise ValueError("invalid signature")
            return state["event"] or {"type": "checkout.session.completed", "data": {}}

    fake.checkout = FakeCheckout
    fake.Webhook = FakeWebhook
    monkeypatch.setitem(sys.modules, "stripe", fake)
    return calls


def _credits_event(account_id, credits=5000, session_id="cs_e2e_1"):
    return {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id,
                "amount_total": 500,
                "metadata": {
                    "kind": "credits",
                    "account_id": account_id,
                    "pack_id": "credits_5",
                    "credits": str(credits),
                },
            }
        },
    }


@pytest.fixture()
def e2e_client(monkeypatch):
    from app.billing.credits import get_ledger
    from app.governance.metering import MeteredPort, SpendingGovernor, reset_metering

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    _install_fake_stripe(monkeypatch)
    main.reset_state()
    reset_metering()
    ledger = get_ledger()
    gov = SpendingGovernor(ledger, daily_cap_credits=100000, monthly_cap_credits=1000000)

    def market():
        return MeteredPort(PaidMockMarketData(), ledger=ledger, governor=gov,
                           tool="aisa.market", estimate_micros=20000)

    def llm():
        return MeteredPort(PaidMockLLM(), ledger=ledger, governor=gov,
                           tool="aisa.llm", estimate_micros=10000)

    def search():
        return MeteredPort(PaidMockSearch(), ledger=ledger, governor=gov,
                           tool="aisa.search", estimate_micros=16000)

    main.app.dependency_overrides[main.get_market_port] = market
    main.app.dependency_overrides[main.get_llm] = llm
    main.app.dependency_overrides[main.get_search] = search
    c = TestClient(main.app)
    yield c, ledger, gov
    main.app.dependency_overrides.clear()


def test_agent_money_end_to_end(e2e_client, monkeypatch):
    c, ledger, gov = e2e_client
    from app.governance.audit import AuditLog  # noqa (audit wired via main)

    # 1. fund the paper account with $10,000
    created = c.post("/api/goals", json={"text": "grow money", "amount": "10000"}).json()
    account_id = created["account_id"]
    goal_id = created["goal_id"]

    # 2. Stripe webhook grants 5000 credits ($5 pack)
    _install_fake_stripe(monkeypatch, event=_credits_event(account_id))
    r = c.post("/api/billing/webhook", content=b'{"id":"evt_e2e"}',
               headers={"stripe-signature": "valid-sig"})
    assert r.status_code == 200
    assert ledger.balance(account_id) == 5000

    # 3. orchestrator invest flow: plan (LLM) + propose (market quotes)
    run = c.post("/api/harness/run",
                 json={"text": "invest $10000 low risk for 5 years",
                       "account_id": account_id}).json()
    assert run["intent"] == "invest"
    assert run["requires_human"] is True
    approval_id = run["results"]["approval_id"]
    assert len(run["results"]["proposed_trades"]) == 4

    # 4. ledger debits equal the mocked AIsa costs, exactly
    debits = [e for e in ledger.list(account_id) if e.kind == "debit"]
    assert len(debits) >= 5  # 1 LLM plan + 4 market quotes
    for d in debits:
        assert d.meta["micros"] in (20000, 5000, 16000)
        assert -d.credits == d.meta["micros"] // 1000
    spent = sum(-d.credits for d in debits)  # debits are stored negative
    assert ledger.balance(account_id) == 5000 - spent
    # each debit names its tool
    tools = {d.tool for d in debits}
    assert any(t.startswith("aisa.llm") for t in tools)
    assert any(t.startswith("aisa.market") for t in tools)

    # 5. human confirms -> paper execution; quotes debited too
    before = ledger.balance(account_id)
    confirmed = c.post("/api/executor/confirm",
                       json={"approval_id": approval_id, "approved": True}).json()
    assert confirmed["status"] == "approved"
    after = ledger.balance(account_id)
    assert after < before  # execution-time quotes were metered
    portfolio = c.get(f"/api/goals/{goal_id}/portfolio").json()
    assert portfolio["total_value"] == "10000.00"
    assert portfolio["cash"] == "0.00"

    # 6. audit log shows the money trail for the run
    audit_entries = c.get(f"/api/audit?account_id={account_id}").json()["entries"]
    summaries = [e for e in audit_entries if e["action"] == "credits.run_summary"]
    assert summaries, "expected a per-run credits summary in the audit log"
    assert summaries[0]["details"]["credits_spent"] == spent
    purchases = [e for e in audit_entries if e["action"] == "credits.purchase"]
    assert purchases and purchases[0]["details"]["credits"] == 5000

    # 7. tiny cap: the next paid call is blocked, balance unchanged
    gov.daily_cap_credits = 1
    gov.monthly_cap_credits = 1000000
    balance_before = ledger.balance(account_id)
    r = c.post("/api/harness/run",
               json={"text": "invest $10000 low risk for 5 years",
                     "account_id": account_id})
    assert r.status_code == 402
    assert "top_up" in r.json()["detail"]
    assert ledger.balance(account_id) == balance_before
