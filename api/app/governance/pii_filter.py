"""PII filter: detect and redact personal data in stored user text.

Adapted from Polygrow's ``governance_layer/pii_filter.py``. Applied to
user-supplied text before it is persisted (goal text, profile preferences).
"""

from __future__ import annotations

import re
from typing import Any, ClassVar


class PIIFilter:
    PATTERNS: ClassVar[dict[str, str]] = {
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "phone": r"\b(?:\+?1[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "credit_card": r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b",
        "ip_address": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
    }

    def detect_pii(self, text: str) -> list[dict[str, str]]:
        findings: list[dict[str, str]] = []
        for pii_type, pattern in self.PATTERNS.items():
            for match in re.finditer(pattern, text):
                findings.append(
                    {
                        "type": pii_type,
                        "start": str(match.start()),
                        "end": str(match.end()),
                    }
                )
        return findings

    def contains_pii(self, text: str) -> bool:
        return any(
            re.search(pattern, text) for pattern in self.PATTERNS.values()
        )

    def redact(self, text: str) -> str:
        redacted = text
        for pii_type, pattern in self.PATTERNS.items():
            redacted = re.sub(pattern, f"[{pii_type.upper()}_REDACTED]", redacted)
        return redacted

    def redact_mapping(self, data: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                out[key] = self.redact(value)
            elif isinstance(value, dict):
                out[key] = self.redact_mapping(value)
            elif isinstance(value, list):
                out[key] = [
                    self.redact_mapping(v)
                    if isinstance(v, dict)
                    else self.redact(v)
                    if isinstance(v, str)
                    else v
                    for v in value
                ]
            else:
                out[key] = value
        return out
