"""Output verifier: schema + safety checks on agent outputs.

Adapted from Polygrow's ``GovernanceVerifier``. Two deliberate differences:
- deterministic safety rules instead of an LLM judge (no extra paid call,
  fully testable);
- finance-specific safety: any guaranteed-returns language ("guaranteed
  profit", "risk-free", ...) fails verification — an investing product must
  never promise returns.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.governance.pii_filter import PIIFilter

_GUARANTEE_PHRASES = (
    "guaranteed profit",
    "guaranteed return",
    "guaranteed gains",
    "risk-free",
    "risk free",
    "can't lose",
    "cannot lose",
    "sure profit",
    "will double",
    "100% safe",
)


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    output: dict | None = None


class OutputVerifier:
    """Verify an agent output mapping against required fields + safety."""

    def __init__(self, pii_filter: PIIFilter | None = None) -> None:
        self._pii = pii_filter or PIIFilter()

    def verify(self, output: dict, required: dict[str, type]) -> VerificationResult:
        errors: list[str] = []
        for name, expected in required.items():
            if name not in output:
                errors.append(f"missing required field: {name}")
                continue
            value = output[name]
            # bool is a subclass of int — don't let it pass as an int field
            ok = isinstance(value, expected) and not (
                expected is int and isinstance(value, bool)
            )
            if not ok:
                errors.append(
                    f"field {name!r} must be {expected.__name__}, "
                    f"got {type(value).__name__}"
                )
        text = " ".join(str(v) for v in output.values() if isinstance(v, str))
        if self._pii.contains_pii(text):
            errors.append("pii detected in output")
        lowered = text.lower()
        for phrase in _GUARANTEE_PHRASES:
            if phrase in lowered:
                errors.append(
                    f"guaranteed-returns language is never allowed: {phrase!r}"
                )
                break
        if errors:
            return VerificationResult(passed=False, errors=errors, output=None)
        return VerificationResult(passed=True, errors=[], output=dict(output))
