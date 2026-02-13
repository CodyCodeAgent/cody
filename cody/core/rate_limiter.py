"""Rate limiting for Cody RPC Server"""

import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    remaining: int
    limit: int
    retry_after: Optional[float] = None


class RateLimiter:
    """Sliding window rate limiter (in-memory).

    Tracks request timestamps and allows up to max_requests within window_seconds.
    """

    def __init__(self, max_requests: int = 60, window_seconds: float = 60.0):
        if max_requests < 1:
            raise ValueError("max_requests must be >= 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        # key → list of request timestamps
        self._requests: dict[str, list[float]] = {}

    @property
    def max_requests(self) -> int:
        return self._max_requests

    @property
    def window_seconds(self) -> float:
        return self._window_seconds

    def _cleanup(self, key: str, now: float) -> None:
        """Remove expired timestamps for a key."""
        if key not in self._requests:
            return
        cutoff = now - self._window_seconds
        self._requests[key] = [t for t in self._requests[key] if t > cutoff]
        if not self._requests[key]:
            del self._requests[key]

    def check(self, key: str = "global") -> RateLimitResult:
        """Check if a request would be allowed (without consuming a slot)."""
        now = time.monotonic()
        self._cleanup(key, now)

        current = len(self._requests.get(key, []))
        remaining = max(0, self._max_requests - current)

        if current >= self._max_requests:
            oldest = self._requests[key][0]
            retry_after = oldest + self._window_seconds - now
            return RateLimitResult(
                allowed=False,
                remaining=0,
                limit=self._max_requests,
                retry_after=max(0.0, retry_after),
            )

        return RateLimitResult(
            allowed=True,
            remaining=remaining,
            limit=self._max_requests,
        )

    def hit(self, key: str = "global") -> RateLimitResult:
        """Record a request and check if it's allowed.

        Returns RateLimitResult indicating whether the request is allowed.
        """
        now = time.monotonic()
        self._cleanup(key, now)

        current = len(self._requests.get(key, []))

        if current >= self._max_requests:
            oldest = self._requests[key][0]
            retry_after = oldest + self._window_seconds - now
            return RateLimitResult(
                allowed=False,
                remaining=0,
                limit=self._max_requests,
                retry_after=max(0.0, retry_after),
            )

        if key not in self._requests:
            self._requests[key] = []
        self._requests[key].append(now)

        remaining = self._max_requests - len(self._requests[key])
        return RateLimitResult(
            allowed=True,
            remaining=remaining,
            limit=self._max_requests,
        )

    def reset(self, key: Optional[str] = None) -> None:
        """Reset rate limits. If key is given, reset only that bucket."""
        if key:
            self._requests.pop(key, None)
        else:
            self._requests.clear()
