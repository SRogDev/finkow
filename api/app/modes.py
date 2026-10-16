"""Operating modes: Real vs Experimental.

Domain invariant (SPEC S8/S9): the two modes never share state — no
operation may read or mutate state across modes. Real mode has NO execution
path wired: every real execution attempt must raise a clear "not configured"
error, never silently fall back to mock simulation.
"""

from __future__ import annotations

from enum import StrEnum

REAL_NOT_CONFIGURED = (
    "real execution is not configured: refusing to move real money. "
    "A brokerage provider, credentials, and compliance review are required "
    "before any real execution path exists. Nothing was simulated."
)


class Mode(StrEnum):
    REAL = "real"
    EXPERIMENTAL = "experimental"


class LiveTradingDisabledError(Exception):
    """Raised whenever anyone tries to touch the (unwired) live-trading path."""


class CrossModeError(Exception):
    """An operation tried to read or mutate state across modes."""


def coerce_mode(value: str) -> Mode:
    """Parse a user-supplied mode string; ValueError on anything else."""
    try:
        return Mode(str(value).strip().lower())
    except ValueError as exc:
        raise ValueError(
            f"mode must be one of {[m.value for m in Mode]}, got {value!r}"
        ) from exc


def check_mode(record_mode: Mode, op_mode: Mode, what: str) -> None:
    """Fail closed when an operation's mode differs from the record's mode."""
    if record_mode is not op_mode:
        raise CrossModeError(
            f"mode mismatch on {what}: record is '{record_mode.value}', "
            f"operation is '{op_mode.value}' — modes never share state"
        )


def is_virtual(mode: Mode) -> bool:
    """True for Experimental Mode: simulated/virtual money, never real."""
    return mode is Mode.EXPERIMENTAL
