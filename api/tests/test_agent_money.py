"""Agent money layer: Stripe-bought credits spent by agents on AIsa calls.

RED phase: pins the credits/metering/governor contract before implementation.

Money model: 1 credit = 1000 micro-USD ($0.001). AIsa's
``x-aisa-customer-cost-micros-usd`` header maps onto credits 1:1 (rounded).
The ledger is append-only; balance is always derived, never stored.
"""

import asyncio
import sys
import types
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.market import Quote
from app.ports import ProviderError


def _run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------------ fakes


class PaidFakeMarketData:
    """Paid test double: every call costs a fixed amount of micro-USD."""

    name = "paid-fake"

    def __init__(self, cost_micros: int = 20000) -> None:
        self._cost_micros = cost_micros
        self.last_cost_micros_usd: int | None = None
        self.calls = 0

    async def get_quote(self, symbol: str) -> Quote:
        self.calls += 1
        self.last_cost_micros_usd = self._cost_micros
        return Quote(
            symbol=symbol.upper(),
            price=Decimal("150.00"),
            currency="USD",
            as_of=datetime.now(UTC),
            provider=self.name,
        )

    async def get_fundamentals(self, symbol: str):
        self.calls += 1
        self.last_cost_micros_usd = self._cost_micros
        return None

    async def get_news(self, symbol: str, limit: int = 5):
        self.calls += 1
        self.last_cost_micros_usd = self._cost_micros
        return []


class PaidFakeLLM:
    name = "paid-fake-llm"

    def __init__(self, cost_micros: int = 5000) -> None:
        self._cost_micros = cost_micros
        self.last_cost_micros_usd: int | None = None
        self.calls = 0

    async def complete(self, messages, *, system="", json_mode=False) -> str:
        self.calls += 1
        self.last_cost_micros_usd = self._cost_micros
        # Valid plan envelope so the GoalPlanner path works end to end.
        if "[finkow-task: goal-plan]" in system:
            return (
                '{"summary_plain": "A calm plan.", "horizon_years": 5, '
                '"risk_level": "low", "allocations": ['
                '{"symbol": "BND", "weight": "0.50", "rationale": "Steady."},'
                '{"symbol": "VTI", "weight": "0.30", "rationale": "Broad."},'
                '{"symbol": "AAPL", "weight": "0.10", "rationale": "Quality."},'
                '{"symbol": "MSFT", "weight": "0.10", "rationale": "Cloud."}]}'
            )
        return "ok (paid fake)"


class PaidFakeSearch:
    name = "paid-fake-search"

    def __init__(self, cost_micros: int = 16000) -> None:
        self._cost_micros = cost_micros
        self.last_cost_micros_usd: int | None = None
        self.calls = 0

    async def search(self, query: str, *, max_results: int = 5):
        self.calls += 1
        self.last_cost_micros_usd = self._cost_micros
        return []


def _install_fake_stripe_credits(monkeypatch, event: dict | None = None):
    """Fake ``stripe`` module: credits checkout + configurable webhook event."""
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
            calls.append(("Webhook.construct_event", signature))
            if signature != "valid-sig":
                raise ValueError("invalid signature")
            return state["event"] or {"type": "checkout.session.completed", "data": {}}

    fake.checkout = FakeCheckout
    fake.Webhook = FakeWebhook
    monkeypatch.setitem(sys.modules, "stripe", fake)
    return calls


def _credits_event(account_id: str, credits: int = 5000, session_id: str = "cs_test_credits_1"):
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


# ------------------------------------------------------------------ ledger


def test_ledger_purchase_and_derived_balance():
    from app.billing.credits import CreditsLedger

    ledger = CreditsLedger()
    entry = ledger.credit("acct-1", 5000, tool="stripe", meta={"pack": "credits_5"})
    assert entry.kind == "purchase"
    assert entry.credits == 5000
    assert ledger.balance("acct-1") == 5000
    # append-only: entries are kept, balance is derived
    assert len(ledger.list("acct-1")) == 1


def test_ledger_debit_reduces_balance():
    from app.billing.credits import CreditsLedger

    ledger = CreditsLedger()
    ledger.credit("acct-1", 5000, tool="stripe")
    entry, shortfall = ledger.debit("acct-1", 20, tool="aisa.market.get_quote")
    assert entry.kind == "debit"
    assert entry.credits == -20
    assert shortfall == 0
    assert ledger.balance("acct-1") == 4980


def test_ledger_debit_beyond_balance_raises_and_changes_nothing():
    from app.billing.credits import CreditsLedger, InsufficientCredits

    ledger = CreditsLedger()
    ledger.credit("acct-1", 10, tool="stripe")
    with pytest.raises(InsufficientCredits):
        ledger.debit("acct-1", 11, tool="aisa.market.get_quote")
    assert ledger.balance("acct-1") == 10
    assert len(ledger.list("acct-1")) == 1  # failed debit leaves no entry


def test_ledger_spent_since_counts_only_debits_in_window():
    from app.billing.credits import CreditsLedger

    ledger = CreditsLedger()
    ledger.credit("acct-1", 5000, tool="stripe")
    ledger.debit("acct-1", 20, tool="aisa.market.get_quote")
    old = datetime.now(UTC) - timedelta(days=40)
    ledger._entries.append(
        __import__("app.billing.credits", fromlist=["CreditEntry"]).CreditEntry(
            id="old", created_at=old, account_id="acct-1",
            kind="debit", credits=-30, tool="aisa.llm.complete", meta={},
        )
    )
    since = datetime.now(UTC) - timedelta(days=30)
    assert ledger.spent_since("acct-1", since) == 20


def test_ledger_credit_is_idempotent_per_stripe_session():
    from app.billing.credits import CreditsLedger

    ledger = CreditsLedger()
    first = ledger.credit_unique("cs_1", "acct-1", 5000, tool="stripe")
    second = ledger.credit_unique("cs_1", "acct-1", 5000, tool="stripe")
    assert first is not None
    assert second is None  # duplicate webhook: no double credit
    assert ledger.balance("acct-1") == 5000


def test_credit_packs_catalog():
    from app.billing.credits import CREDIT_PACKS

    assert CREDIT_PACKS["credits_5"].usd_cents == 500
    assert CREDIT_PACKS["credits_5"].credits == 5000
    assert CREDIT_PACKS["credits_20"].credits == 20000
    assert CREDIT_PACKS["credits_50"].credits == 50000


def test_micros_to_credits_rounding():
    from app.billing.credits import micros_to_credits

    assert micros_to_credits(20000) == 20
    assert micros_to_credits(16000) == 16
    assert micros_to_credits(5000) == 5
    assert micros_to_credits(0) == 0


# ------------------------------------------------------------------ metering


def _metered(port, ledger, governor, tool="test.tool", estimate_micros=20000,
             max_price_usd=None):
    from app.governance.metering import MeteredPort

    return MeteredPort(
        port, ledger=ledger, governor=governor, tool=tool,
        estimate_micros=estimate_micros, max_price_usd=max_price_usd,
    )


def _governor(ledger, daily=1000, monthly=10000):
    from app.governance.metering import SpendingGovernor

    return SpendingGovernor(ledger, daily_cap_credits=daily, monthly_cap_credits=monthly)


def _ctx(account_id):
    from app.governance.metering import account_context

    return account_context(account_id)


def test_metered_port_debits_actual_reported_cost():
    from app.billing.credits import CreditsLedger

    ledger = CreditsLedger()
    ledger.credit("acct-1", 5000, tool="stripe")
    port = _metered(PaidFakeMarketData(cost_micros=20000), ledger, _governor(ledger))
    with _ctx("acct-1"):
        quote = _run(port.get_quote("AAPL"))
    assert quote.price == Decimal("150.00")
    # 20000 micros -> 20 credits debited, exactly
    assert ledger.balance("acct-1") == 4980
    debits = [e for e in ledger.list("acct-1") if e.kind == "debit"]
    assert len(debits) == 1
    assert debits[0].tool == "test.tool.get_quote"
    assert debits[0].meta["micros"] == 20000


def test_metered_port_falls_back_to_estimate_without_cost_header():
    from app.billing.credits import CreditsLedger

    ledger = CreditsLedger()
    ledger.credit("acct-1", 5000, tool="stripe")

    class NoHeader(PaidFakeMarketData):
        async def get_quote(self, symbol):
            q = await super().get_quote(symbol)
            self.last_cost_micros_usd = None  # header absent: use estimate
            return q

    port = _metered(NoHeader(), ledger, _governor(ledger), estimate_micros=20000)
    with _ctx("acct-1"):
        _run(port.get_quote("AAPL"))
    assert ledger.balance("acct-1") == 4980  # estimate 20000 micros -> 20 credits


def test_metered_port_skips_free_calls():
    from app.billing.credits import CreditsLedger
    from app.providers.mock import MockMarketData

    ledger = CreditsLedger()
    ledger.credit("acct-1", 5000, tool="stripe")
    port = _metered(MockMarketData(), ledger, _governor(ledger))
    with _ctx("acct-1"):
        _run(port.get_quote("AAPL"))
    assert ledger.balance("acct-1") == 5000
    assert ledger.list("acct-1") == [e for e in ledger.list("acct-1") if e.kind == "purchase"]


def test_metered_port_passes_through_without_account():
    from app.billing.credits import CreditsLedger

    ledger = CreditsLedger()
    port = _metered(PaidFakeMarketData(), ledger, _governor(ledger))
    quote = _run(port.get_quote("AAPL"))  # no account context: no metering
    assert quote.price == Decimal("150.00")
    assert ledger.balance("nope") == 0


def test_credits_exhausted_is_a_provider_error():
    from app.governance.metering import CreditsExhausted

    assert issubclass(CreditsExhausted, ProviderError)


def test_governor_blocks_zero_balance_before_call():
    from app.billing.credits import CreditsLedger
    from app.governance.metering import CreditsExhausted

    ledger = CreditsLedger()  # no credits at all
    inner = PaidFakeMarketData()
    port = _metered(inner, ledger, _governor(ledger))
    with _ctx("acct-1"):
        with pytest.raises(CreditsExhausted):
            _run(port.get_quote("AAPL"))
    assert inner.calls == 0  # the paid call never happened


def test_governor_blocks_when_daily_cap_would_be_exceeded():
    from app.billing.credits import CreditsLedger
    from app.governance.metering import CreditsExhausted

    ledger = CreditsLedger()
    ledger.credit("acct-1", 5000, tool="stripe")
    gov = _governor(ledger, daily=25, monthly=100000)
    inner = PaidFakeMarketData(cost_micros=20000)  # 20 credits/call
    port = _metered(inner, ledger, gov)
    with _ctx("acct-1"):
        _run(port.get_quote("AAPL"))  # 20 spent, ok
        with pytest.raises(CreditsExhausted):
            _run(port.get_quote("MSFT"))  # 20 more would exceed the 25 cap
    assert inner.calls == 1
    assert ledger.balance("acct-1") == 4980  # blocked call changed nothing


def test_governor_monthly_cap():
    from app.billing.credits import CreditsLedger
    from app.governance.metering import CreditsExhausted

    ledger = CreditsLedger()
    ledger.credit("acct-1", 5000, tool="stripe")
    gov = _governor(ledger, daily=100000, monthly=25)
    port = _metered(PaidFakeMarketData(cost_micros=20000), ledger, gov)
    with _ctx("acct-1"):
        _run(port.get_quote("AAPL"))
        with pytest.raises(CreditsExhausted):
            _run(port.get_quote("MSFT"))


def test_max_price_usd_guard_refuses_expensive_call_upfront():
    from app.billing.credits import CreditsLedger
    from app.governance.metering import CreditsExhausted

    ledger = CreditsLedger()
    ledger.credit("acct-1", 5000, tool="stripe")
    inner = PaidFakeMarketData(cost_micros=20000)  # $0.02 estimate
    port = _metered(inner, ledger, _governor(ledger), max_price_usd=0.001)
    with _ctx("acct-1"):
        with pytest.raises(CreditsExhausted):
            _run(port.get_quote("AAPL"))
    assert inner.calls == 0


def test_market_fallback_on_credits_exhausted():
    """Exhausted credits fall back to the free direct path for quotes."""
    from app.billing.credits import CreditsLedger
    from app.providers.cached import FallbackMarketData

    ledger = CreditsLedger()  # zero balance
    primary = _metered(PaidFakeMarketData(), ledger, _governor(ledger))

    class FreeFake:
        name = "free-fake"
        last_cost_micros_usd = 0

        async def get_quote(self, symbol):
            return Quote(symbol=symbol, price=Decimal("1.00"), currency="USD",
                         as_of=datetime.now(UTC), provider=self.name)

        async def get_fundamentals(self, symbol):
            return None

        async def get_news(self, symbol, limit=5):
            return []

    port = FallbackMarketData(primary, FreeFake())
    with _ctx("acct-1"):
        quote = _run(port.get_quote("AAPL"))
    assert quote.price == Decimal("1.00")
    assert quote.provider == "free-fake"


# ------------------------------------------------------------------ cost header


def test_aisa_market_data_captures_cost_header():
    import httpx

    from app.providers.aisa import AisaMarketData

    async def handler(request):
        return httpx.Response(
            200,
            headers={"x-aisa-customer-cost-micros-usd": "20000"},
            json={"data": [{"close": 150.0}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = AisaMarketData("k", client=client)
    quote = _run(adapter.get_quote("AAPL"))
    assert quote.price == Decimal("150.0")
    assert adapter.last_cost_micros_usd == 20000


def test_aisa_llm_captures_cost_header():
    import httpx

    from app.ports import ChatMessage
    from app.providers.aisa import AisaLLM

    async def handler(request):
        return httpx.Response(
            200,
            headers={"X-AISA-CUSTOMER-COST-MICROS-USD": "1370"},
            json={"choices": [{"message": {"content": "hi"}}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = AisaLLM("k", client=client)
    text = _run(adapter.complete([ChatMessage(role="user", content="hi")]))
    assert text == "hi"
    assert adapter.last_cost_micros_usd == 1370


def test_aisa_search_captures_cost_header():
    import httpx

    from app.providers.aisa import AisaWebSearch

    async def handler(request):
        return httpx.Response(
            200,
            headers={"x-aisa-customer-cost-micros-usd": "16000"},
            json={"results": []},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = AisaWebSearch("k", client=client)
    assert _run(adapter.search("x")) == []
    assert adapter.last_cost_micros_usd == 16000


def test_mocks_report_zero_cost():
    from app.providers.direct import DirectQuoteAdapter
    from app.providers.mock import MockLLM, MockMarketData, MockWebSearch

    assert MockMarketData.last_cost_micros_usd == 0
    assert MockLLM.last_cost_micros_usd == 0
    assert MockWebSearch.last_cost_micros_usd == 0
    assert DirectQuoteAdapter.last_cost_micros_usd == 0
