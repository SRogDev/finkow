"""In-memory rate limiter for paid provider calls.

Adapted from Polygrow's Redis-backed limiter: same fixed-window semantics,
no infrastructure. Wrap AIsa (paid) ports so a runaway agent cannot burn the
key — ``RateLimitExceeded`` subclasses ``ProviderError`` so existing
fallback chains keep working.
"""

from __future__ import annotations

import time

from app.ports import ProviderError


class RateLimitExceeded(ProviderError):
    """Raised when a caller exceeds its paid-call budget for the window."""


class RateLimiter:
    """Fixed-window counter per key."""

    def __init__(self, max_calls: int, window_seconds: float) -> None:
        if max_calls <= 0:
            raise ValueError("max_calls must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._max = max_calls
        self._window = window_seconds
        self._windows: dict[str, tuple[float, int]] = {}

    def _current(self, key: str) -> tuple[float, int]:
        now = time.monotonic()
        start, count = self._windows.get(key, (now, 0))
        if now - start >= self._window:
            start, count = now, 0
        return start, count

    def acquire(self, key: str) -> bool:
        """Consume one call if budget remains. Returns False when exhausted."""
        start, count = self._current(key)
        if count >= self._max:
            self._windows[key] = (start, count)
            return False
        self._windows[key] = (start, count + 1)
        return True

    def check(self, key: str) -> None:
        """Acquire or raise — for wrapping provider calls."""
        if not self.acquire(key):
            raise RateLimitExceeded(f"rate limit exceeded for {key}")

    def status(self, key: str) -> dict:
        _, count = self._current(key)
        return {
            "key": key,
            "limit": self._max,
            "used": count,
            "remaining": max(0, self._max - count),
            "window_seconds": self._window,
        }

    def reset(self, key: str) -> None:
        self._windows.pop(key, None)


def wrap_port(port, limiter: RateLimiter, key: str):
    """Guard a provider port: every method call first acquires rate budget.

    ``RateLimitExceeded`` subclasses ``ProviderError``, so existing fallback
    chains treat an exhausted budget like any other provider failure.
    Only async methods are wrapped; plain attributes pass through.
    """

    class _Guard:
        def __init__(self, wrapped) -> None:
            self._wrapped = wrapped
            self.name = getattr(wrapped, "name", "guarded")

        def __getattr__(self, name: str):
            attr = getattr(self._wrapped, name)
            if not callable(attr):
                return attr

            async def checked(*args, **kwargs):
                limiter.check(key)
                return await attr(*args, **kwargs)

            return checked

    return _Guard(port)
