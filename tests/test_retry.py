"""Tests for LLM API retry module."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from cody.core.config import RetryConfig as RetryConfigPydantic
from cody.core.retry import (
    RetryConfig,
    is_retryable,
    with_retry,
    with_retry_sync,
)


# ── is_retryable ──────────────────────────────────────────────────────────


def test_retryable_429():
    exc = Exception("Error code: 429 Too Many Requests")
    assert is_retryable(exc) is True


def test_retryable_500():
    exc = Exception("status 500 internal server error")
    assert is_retryable(exc) is True


def test_retryable_502():
    exc = Exception("Bad Gateway 502")
    assert is_retryable(exc) is True


def test_retryable_503():
    exc = Exception("503 service unavailable")
    assert is_retryable(exc) is True


def test_retryable_529():
    exc = Exception("status: 529")
    assert is_retryable(exc) is True


def test_retryable_rate_limit_keyword():
    exc = Exception("rate limit exceeded, please retry")
    assert is_retryable(exc) is True


def test_retryable_overloaded():
    exc = Exception("The model is currently overloaded")
    assert is_retryable(exc) is True


def test_retryable_connection_error():
    exc = Exception("connection reset by peer")
    assert is_retryable(exc) is True


def test_retryable_timeout():
    exc = Exception("request timed out")
    assert is_retryable(exc) is True


def test_not_retryable_context_length():
    exc = Exception("context_length_exceeded: max 128000 tokens")
    assert is_retryable(exc) is False


def test_not_retryable_invalid_api_key():
    exc = Exception("invalid_api_key: check your API key")
    assert is_retryable(exc) is False


def test_not_retryable_auth():
    exc = Exception("authentication failed")
    assert is_retryable(exc) is False


def test_not_retryable_generic():
    exc = Exception("some unknown error happened")
    assert is_retryable(exc) is False


def test_non_retryable_takes_precedence():
    """Non-retryable keywords beat retryable status codes."""
    exc = Exception("429 context_length_exceeded")
    assert is_retryable(exc) is False


# ── with_retry (async) ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_with_retry_success_no_retry():
    """Successful call returns immediately without retry."""
    fn = AsyncMock(return_value="ok")
    result = await with_retry(fn, "arg1", retry_config=RetryConfig(max_retries=3))
    assert result == "ok"
    assert fn.call_count == 1


@pytest.mark.asyncio
async def test_with_retry_transient_then_success():
    """Retries on transient error, then succeeds."""
    fn = AsyncMock(side_effect=[
        Exception("429 rate limit"),
        Exception("502 bad gateway"),
        "ok",
    ])
    result = await with_retry(
        fn, retry_config=RetryConfig(max_retries=3, base_delay=0.01),
    )
    assert result == "ok"
    assert fn.call_count == 3


@pytest.mark.asyncio
async def test_with_retry_exhausted():
    """Raises after max retries exhausted."""
    fn = AsyncMock(side_effect=Exception("429 rate limit"))
    with pytest.raises(Exception, match="429"):
        await with_retry(
            fn, retry_config=RetryConfig(max_retries=2, base_delay=0.01),
        )
    assert fn.call_count == 3  # initial + 2 retries


@pytest.mark.asyncio
async def test_with_retry_non_retryable_fails_fast():
    """Non-retryable errors are raised immediately."""
    fn = AsyncMock(side_effect=Exception("context_length_exceeded"))
    with pytest.raises(Exception, match="context_length"):
        await with_retry(
            fn, retry_config=RetryConfig(max_retries=3, base_delay=0.01),
        )
    assert fn.call_count == 1  # no retry


@pytest.mark.asyncio
async def test_with_retry_disabled():
    """Disabled retry passes through directly."""
    fn = AsyncMock(side_effect=Exception("429 rate limit"))
    with pytest.raises(Exception, match="429"):
        await with_retry(
            fn, retry_config=RetryConfig(enabled=False),
        )
    assert fn.call_count == 1


@pytest.mark.asyncio
async def test_with_retry_passes_args():
    """Arguments and kwargs are forwarded correctly."""
    fn = AsyncMock(return_value="ok")
    result = await with_retry(
        fn, "a", "b", key="val",
        retry_config=RetryConfig(max_retries=1),
    )
    assert result == "ok"
    fn.assert_called_once_with("a", "b", key="val")


# ── with_retry_sync ───────────────────────────────────────────────────────


def test_with_retry_sync_success():
    fn = MagicMock(return_value="ok")
    result = with_retry_sync(fn, retry_config=RetryConfig(max_retries=2))
    assert result == "ok"
    assert fn.call_count == 1


def test_with_retry_sync_transient_then_success():
    fn = MagicMock(side_effect=[
        Exception("429 rate limit"),
        "ok",
    ])
    result = with_retry_sync(
        fn, retry_config=RetryConfig(max_retries=2, base_delay=0.01),
    )
    assert result == "ok"
    assert fn.call_count == 2


def test_with_retry_sync_exhausted():
    fn = MagicMock(side_effect=Exception("500 server error"))
    with pytest.raises(Exception, match="500"):
        with_retry_sync(
            fn, retry_config=RetryConfig(max_retries=1, base_delay=0.01),
        )
    assert fn.call_count == 2


def test_with_retry_sync_non_retryable():
    fn = MagicMock(side_effect=Exception("invalid_api_key"))
    with pytest.raises(Exception, match="invalid_api_key"):
        with_retry_sync(
            fn, retry_config=RetryConfig(max_retries=3, base_delay=0.01),
        )
    assert fn.call_count == 1


# ── RetryConfig in Config ────────────────────────────────────────────────


def test_retry_config_defaults():
    """RetryConfig has sensible defaults."""
    from cody.core.config import Config
    cfg = Config()
    assert cfg.retry.enabled is True
    assert cfg.retry.max_retries == 3
    assert cfg.retry.base_delay == 2.0
    assert cfg.retry.max_delay == 30.0


def test_retry_config_pydantic_model():
    """RetryConfig is a proper pydantic model."""
    rc = RetryConfigPydantic(enabled=False, max_retries=5, base_delay=1.0, max_delay=60.0)
    assert rc.enabled is False
    assert rc.max_retries == 5
