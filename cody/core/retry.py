"""LLM API retry with exponential backoff.

Wraps async callables to retry on transient LLM provider errors
(rate limit 429, server errors 5xx). Does NOT retry on client errors
(bad request, auth failure) or context overflow.
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# HTTP status codes that warrant a retry.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 529}

# Keywords in exception messages that indicate a transient failure.
_RETRYABLE_KEYWORDS = (
    "rate limit",
    "overloaded",
    "too many requests",
    "server error",
    "connection",
    "timed out",
    "timeout",
    "service unavailable",
    "bad gateway",
    "internal server error",
)

# Keywords that indicate non-retryable errors (fail fast).
_NON_RETRYABLE_KEYWORDS = (
    "context_length_exceeded",
    "context window",
    "maximum context",
    "invalid_api_key",
    "authentication",
    "permission",
    "invalid_request",
)


@dataclass
class RetryConfig:
    """Configuration for LLM API retry behaviour."""
    max_retries: int = 3
    base_delay: float = 2.0
    max_delay: float = 30.0
    enabled: bool = True


def is_retryable(exc: Exception) -> bool:
    """Determine whether an exception represents a transient failure.

    Returns ``True`` for rate-limit (429) and server errors (5xx).
    Returns ``False`` for client errors, auth failures, and context overflow.
    """
    msg = str(exc).lower()

    # Fast reject: non-retryable keywords take precedence.
    if any(kw in msg for kw in _NON_RETRYABLE_KEYWORDS):
        return False

    # Check for retryable HTTP status codes in the message.
    # Use word boundary to avoid false positives (e.g. "port 5029" matching 502).
    for code in _RETRYABLE_STATUS_CODES:
        if re.search(rf'\b{code}\b', msg):
            return True

    # Check for retryable keywords.
    return any(kw in msg for kw in _RETRYABLE_KEYWORDS)


async def with_retry(
    fn,
    *args,
    retry_config: RetryConfig | None = None,
    **kwargs,
):
    """Call *fn* with exponential backoff on transient LLM errors.

    Only retries when :func:`is_retryable` returns ``True``.
    Raises the original exception immediately for non-retryable errors.
    """
    cfg = retry_config or RetryConfig()
    if not cfg.enabled:
        return await fn(*args, **kwargs)

    last_exc: Exception | None = None
    for attempt in range(cfg.max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt >= cfg.max_retries or not is_retryable(exc):
                raise
            delay = min(cfg.base_delay * (2 ** attempt), cfg.max_delay)
            logger.warning(
                "LLM call failed (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1, cfg.max_retries, delay, exc,
            )
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]  # unreachable, satisfies type checker


def with_retry_sync(
    fn,
    *args,
    retry_config: RetryConfig | None = None,
    **kwargs,
):
    """Synchronous version of :func:`with_retry`.

    Uses ``time.sleep`` instead of ``asyncio.sleep``.
    """
    import time

    cfg = retry_config or RetryConfig()
    if not cfg.enabled:
        return fn(*args, **kwargs)

    last_exc: Exception | None = None
    for attempt in range(cfg.max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt >= cfg.max_retries or not is_retryable(exc):
                raise
            delay = min(cfg.base_delay * (2 ** attempt), cfg.max_delay)
            logger.warning(
                "LLM call failed (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1, cfg.max_retries, delay, exc,
            )
            time.sleep(delay)
    raise last_exc  # type: ignore[misc]  # unreachable, satisfies type checker
