"""Execution-provider contract: what a real brokerage integration must
satisfy — and proof the mock can never be mistaken for one."""

from decimal import Decimal

import pytest

from app.brokerage import LiveTradingDisabledError, OrderSide
from app.execution_provider import (
    ExecutionProvider,
    MockExecutionProvider,
    ProviderAccountInfo,
    ProviderAccountRef,
    ProviderCapabilities,
    ProviderOrderRequest,
    ProviderOrderResult,
    RealExecutionContractError,
    assert_real_execution_result,
)
from app.modes import Mode
from app.orders import OrderStatus


def _experimental_ref() -> ProviderAccountRef:
    return ProviderAccountRef(
        account_id="acct-1", owner_user_id="user-1", mode=Mode.EXPERIMENTAL
    )


def _real_ref() -> ProviderAccountRef:
    return ProviderAccountRef(
        account_id="acct-1", owner_user_id="user-1", mode=Mode.REAL
    )


def _request() -> ProviderOrderRequest:
    return ProviderOrderRequest(
        symbol="AAPL",
        side=OrderSide.BUY,
        qty=Decimal("10"),
        order_type="market",
        time_in_force="day",
        idempotency_key="idem-1",
    )


def _run(coro):
    import asyncio

    return asyncio.run(coro)


# ---------------------------------------------------------------- contract


def test_mock_implements_the_provider_protocol():
    provider = MockExecutionProvider()
    assert isinstance(provider, ExecutionProvider)
    for method in (
        "submit", "cancel", "get_order", "list_open_orders",
        "sync_positions", "get_account_info",
    ):
        assert callable(getattr(provider, method)), method
    assert isinstance(provider.capabilities, ProviderCapabilities)
    assert provider.name


def test_mock_capabilities_admit_no_real_execution():
    caps = MockExecutionProvider().capabilities
    assert caps.real_execution is False
    assert caps.provides_provider_order_ids is False
    assert caps.partial_fills is False
    assert caps.real_settlement is False


def test_mock_submit_is_always_simulated_and_has_no_provider_order_id():
    provider = MockExecutionProvider()
    result = _run(provider.submit(_experimental_ref(), _request()))
    assert isinstance(result, ProviderOrderResult)
    assert result.simulated is True
    assert result.provider_order_id is None  # no real provider involved
    assert result.status == OrderStatus.FILLED


def test_mock_never_simulates_a_real_order():
    provider = MockExecutionProvider()
    with pytest.raises(LiveTradingDisabledError):
        _run(provider.submit(_real_ref(), _request()))


def test_mock_cancel_and_status_queries_have_no_provider_state():
    provider = MockExecutionProvider()
    _run(provider.submit(_experimental_ref(), _request()))
    # no provider order id -> nothing real to cancel or query
    with pytest.raises(RealExecutionContractError):
        _run(provider.cancel(_experimental_ref(), "provider-123"))
    assert _run(provider.get_order(_experimental_ref(), "provider-123")) is None
    assert _run(provider.list_open_orders(_experimental_ref())) == []


def test_mock_positions_and_account_are_virtual():
    provider = MockExecutionProvider()
    positions = _run(provider.sync_positions(_experimental_ref()))
    info = _run(provider.get_account_info(_experimental_ref()))
    assert isinstance(info, ProviderAccountInfo)
    assert info.currency == "USD"
    assert info.live is False
    assert all(p.simulated for p in positions)


def test_real_execution_result_requires_provider_order_id():
    """The real path's gate: any result without a provider order id is
    rejected, so mock output can never flow into real execution."""
    provider = MockExecutionProvider()
    result = _run(provider.submit(_experimental_ref(), _request()))
    with pytest.raises(RealExecutionContractError):
        assert_real_execution_result(result)


def test_real_execution_result_rejects_simulated_results():
    result = ProviderOrderResult(
        provider_order_id="real-123",
        symbol="AAPL",
        side=OrderSide.BUY,
        qty=Decimal("10"),
        status=OrderStatus.FILLED,
        simulated=True,  # simulated even with an id: still not real
    )
    with pytest.raises(RealExecutionContractError):
        assert_real_execution_result(result)


def test_order_request_requires_idempotency_key_for_real():
    with pytest.raises(ValueError, match="idempotency_key"):
        ProviderOrderRequest(
            symbol="AAPL", side=OrderSide.BUY, qty=Decimal("1"),
            order_type="market", time_in_force="day", idempotency_key="",
        )
