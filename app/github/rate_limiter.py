"""Rate Limit Handler — tracks GitHub's rate-limit headers and computes waits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass
class RateLimitState:
    limit: Optional[int] = None
    remaining: Optional[int] = None
    reset_epoch: Optional[int] = None


class RateLimiter:
    """Stateful helper that interprets ``X-RateLimit-*`` headers.

    It does not sleep on its own (so it stays unit-testable); callers ask
    :meth:`seconds_until_reset` / :meth:`should_throttle` and decide how to wait.
    """

    def __init__(self, min_remaining: int = 1) -> None:
        self.min_remaining = min_remaining
        self.state = RateLimitState()

    def update_from_headers(self, headers: Mapping[str, str]) -> RateLimitState:
        lower = {k.lower(): v for k, v in headers.items()}

        def _int(key: str) -> Optional[int]:
            val = lower.get(key)
            try:
                return int(val) if val is not None else None
            except (TypeError, ValueError):
                return None

        self.state = RateLimitState(
            limit=_int("x-ratelimit-limit"),
            remaining=_int("x-ratelimit-remaining"),
            reset_epoch=_int("x-ratelimit-reset"),
        )
        return self.state

    def should_throttle(self) -> bool:
        if self.state.remaining is None:
            return False
        return self.state.remaining <= self.min_remaining - 1 or self.state.remaining == 0

    def seconds_until_reset(self, now_epoch: float) -> float:
        if self.state.reset_epoch is None:
            return 0.0
        return max(0.0, float(self.state.reset_epoch) - float(now_epoch))

    def is_rate_limited_response(self, status_code: int, headers: Mapping[str, str]) -> bool:
        """A 403/429 with ``remaining == 0`` is a hard rate-limit hit."""
        if status_code not in (403, 429):
            return False
        self.update_from_headers(headers)
        return self.state.remaining == 0
