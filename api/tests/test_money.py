"""Money math must be exact — Decimal everywhere, no float money bugs."""

from decimal import Decimal

from app.money import to_cash, to_qty


def test_to_cash_quantizes_to_cents_half_up():
    assert to_cash(Decimal("10.005")) == Decimal("10.01")
    assert to_cash(Decimal("10.004")) == Decimal("10.00")
    assert to_cash("99.9") == Decimal("99.90")
    assert to_cash(100) == Decimal("100.00")


def test_to_cash_never_returns_float():
    result = to_cash(Decimal("1") / Decimal("3"))
    assert isinstance(result, Decimal)
    assert result == Decimal("0.33")


def test_to_qty_supports_fractional_crypto():
    assert to_qty("0.00000001") == Decimal("0.00000001")
    assert to_qty(Decimal("1.5")) == Decimal("1.50000000")


def test_position_cost_is_exact():
    # 10 shares @ $150.005 -> $1500.05 (rounded half-up on total)
    qty, price = Decimal("10"), Decimal("150.005")
    cost = to_cash(qty * price)
    assert cost == Decimal("1500.05")


def test_buy_reduces_cash_exactly():
    cash, cost = Decimal("100000.00"), Decimal("1500.05")
    assert to_cash(cash - cost) == Decimal("98499.95")
