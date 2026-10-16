"""Exact money math: Decimal everywhere, quantized at system boundaries.

Rule: parse/quantize on input, compute in full precision, quantize on output.
Never let a float touch money.
"""

from decimal import ROUND_HALF_UP, Decimal

CASH_QUANTUM = Decimal("0.01")
QTY_QUANTUM = Decimal("0.00000001")  # fractional shares / crypto
ALLOC_QUANTUM = Decimal("0.0001")


def to_cash(value: Decimal | str | int) -> Decimal:
    """Quantize to cents, half-up. Use for cash balances, costs, P&L."""
    return Decimal(str(value)).quantize(CASH_QUANTUM, rounding=ROUND_HALF_UP)


def to_qty(value: Decimal | str | int) -> Decimal:
    """Quantize to 8 dp. Use for position quantities."""
    return Decimal(str(value)).quantize(QTY_QUANTUM, rounding=ROUND_HALF_UP)


def cash_str(value: Decimal) -> str:
    """Stable 2-dp string for API responses."""
    return format(to_cash(value), ".2f")


def qty_str(value: Decimal) -> str:
    """Trimmed string for quantities (e.g. '10', '0.5')."""
    return format(to_qty(value).normalize(), "f")
