"""Tests for rate limiting"""

import time

import pytest

from cody.core.rate_limiter import RateLimiter, RateLimitResult


# ── constructor ──────────────────────────────────────────────────────────────


def test_constructor_defaults():
    limiter = RateLimiter()
    assert limiter.max_requests == 60
    assert limiter.window_seconds == 60.0


def test_constructor_custom():
    limiter = RateLimiter(max_requests=10, window_seconds=30.0)
    assert limiter.max_requests == 10
    assert limiter.window_seconds == 30.0


def test_constructor_invalid_max_requests():
    with pytest.raises(ValueError, match="max_requests"):
        RateLimiter(max_requests=0)


def test_constructor_invalid_window():
    with pytest.raises(ValueError, match="window_seconds"):
        RateLimiter(window_seconds=0)


# ── check (read-only) ───────────────────────────────────────────────────────


def test_check_allowed():
    limiter = RateLimiter(max_requests=5, window_seconds=60.0)
    result = limiter.check("client1")
    assert result.allowed is True
    assert result.remaining == 5
    assert result.limit == 5


def test_check_does_not_consume():
    limiter = RateLimiter(max_requests=2, window_seconds=60.0)
    limiter.check("client1")
    limiter.check("client1")
    limiter.check("client1")
    # check doesn't consume, so hit should still be allowed
    result = limiter.hit("client1")
    assert result.allowed is True


# ── hit ──────────────────────────────────────────────────────────────────────


def test_hit_allowed():
    limiter = RateLimiter(max_requests=3, window_seconds=60.0)
    result = limiter.hit("client1")
    assert result.allowed is True
    assert result.remaining == 2
    assert result.limit == 3


def test_hit_exhausts_limit():
    limiter = RateLimiter(max_requests=3, window_seconds=60.0)

    for _ in range(3):
        result = limiter.hit("client1")
        assert result.allowed is True

    # Fourth request should be denied
    result = limiter.hit("client1")
    assert result.allowed is False
    assert result.remaining == 0
    assert result.retry_after is not None
    assert result.retry_after > 0


def test_hit_different_keys_independent():
    limiter = RateLimiter(max_requests=2, window_seconds=60.0)

    limiter.hit("client1")
    limiter.hit("client1")

    # client2 should be unaffected
    result = limiter.hit("client2")
    assert result.allowed is True
    assert result.remaining == 1


def test_hit_default_key():
    limiter = RateLimiter(max_requests=2, window_seconds=60.0)
    result = limiter.hit()
    assert result.allowed is True


# ── window expiry ────────────────────────────────────────────────────────────


def test_window_expiry():
    limiter = RateLimiter(max_requests=2, window_seconds=0.1)

    limiter.hit("client1")
    limiter.hit("client1")
    result = limiter.hit("client1")
    assert result.allowed is False

    # Wait for window to expire
    time.sleep(0.15)

    result = limiter.hit("client1")
    assert result.allowed is True


# ── reset ────────────────────────────────────────────────────────────────────


def test_reset_specific_key():
    limiter = RateLimiter(max_requests=2, window_seconds=60.0)

    limiter.hit("client1")
    limiter.hit("client1")
    limiter.hit("client2")

    limiter.reset("client1")

    # client1 should be reset
    result = limiter.hit("client1")
    assert result.allowed is True
    assert result.remaining == 1

    # client2 should still have 1 hit
    result = limiter.check("client2")
    assert result.remaining == 1


def test_reset_all():
    limiter = RateLimiter(max_requests=2, window_seconds=60.0)

    limiter.hit("client1")
    limiter.hit("client2")

    limiter.reset()

    result = limiter.hit("client1")
    assert result.allowed is True
    assert result.remaining == 1


# ── RateLimitResult ──────────────────────────────────────────────────────────


def test_rate_limit_result_defaults():
    result = RateLimitResult(allowed=True, remaining=5, limit=10)
    assert result.retry_after is None


def test_rate_limit_result_with_retry():
    result = RateLimitResult(allowed=False, remaining=0, limit=10, retry_after=5.5)
    assert result.retry_after == 5.5


# ── remaining count accuracy ─────────────────────────────────────────────────


def test_remaining_decreases():
    limiter = RateLimiter(max_requests=5, window_seconds=60.0)

    r1 = limiter.hit("key")
    assert r1.remaining == 4

    r2 = limiter.hit("key")
    assert r2.remaining == 3

    r3 = limiter.hit("key")
    assert r3.remaining == 2
