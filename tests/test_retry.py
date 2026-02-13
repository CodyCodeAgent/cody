"""Tests for SDK auto-reconnect / retry with exponential backoff"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from cody.client import (
    AsyncCodyClient,
    CodyClient,
    CodyConnectionError,
    _backoff_delay,
    _handle_error,
    _extract_error,
    CodyNotFoundError,
    CodyError,
)


# ── Backoff delay ───────────────────────────────────────────────────────────


def test_backoff_delay_values():
    assert _backoff_delay(0) == 0.5
    assert _backoff_delay(1) == 1.0
    assert _backoff_delay(2) == 2.0
    assert _backoff_delay(3) == 4.0
    assert _backoff_delay(4) == 8.0  # capped


def test_backoff_delay_capped():
    assert _backoff_delay(10) == 8.0  # still capped at 8.0


# ── Error extraction ────────────────────────────────────────────────────────


def test_extract_error_structured():
    resp = httpx.Response(200, json={"error": {"code": "TOOL_ERROR", "message": "broken"}})
    msg, code = _extract_error(resp)
    assert msg == "broken"
    assert code == "TOOL_ERROR"


def test_extract_error_legacy():
    resp = httpx.Response(200, json={"detail": "old error"})
    msg, code = _extract_error(resp)
    assert msg == "old error"
    assert code is None


def test_extract_error_plain_text():
    resp = httpx.Response(200, text="just text")
    msg, code = _extract_error(resp)
    assert msg == "just text"
    assert code is None


def test_handle_error_ok():
    resp = httpx.Response(200, json={})
    _handle_error(resp)  # should not raise


def test_handle_error_404():
    resp = httpx.Response(404, json={"error": {"code": "SESSION_NOT_FOUND", "message": "nope"}})
    with pytest.raises(CodyNotFoundError) as exc_info:
        _handle_error(resp)
    assert exc_info.value.code == "SESSION_NOT_FOUND"
    assert exc_info.value.status_code == 404


def test_handle_error_500():
    resp = httpx.Response(500, json={"error": {"code": "SERVER_ERROR", "message": "boom"}})
    with pytest.raises(CodyError) as exc_info:
        _handle_error(resp)
    assert exc_info.value.status_code == 500


# ── Sync client retry ──────────────────────────────────────────────────────


def test_sync_retry_success_first_attempt():
    """No retry needed when first attempt succeeds"""
    client = CodyClient("http://localhost:8000", max_retries=3)
    client._client = MagicMock()
    client._client.get.return_value = httpx.Response(200, json={"status": "ok", "version": "0.1.0"})

    result = client.health()
    assert result["status"] == "ok"
    assert client._client.get.call_count == 1


def test_sync_retry_on_connect_error():
    """Retry on connection error, eventually succeed"""
    client = CodyClient("http://localhost:8000", max_retries=2)
    client._client = MagicMock()

    # First two calls fail, third succeeds
    client._client.get.side_effect = [
        httpx.ConnectError("refused"),
        httpx.ConnectError("refused"),
        httpx.Response(200, json={"status": "ok", "version": "0.1.0"}),
    ]

    with patch("cody.client.time.sleep"):  # skip actual sleep
        result = client.health()

    assert result["status"] == "ok"
    assert client._client.get.call_count == 3


def test_sync_retry_exhausted():
    """Raise CodyConnectionError when all retries exhausted"""
    client = CodyClient("http://localhost:8000", max_retries=2)
    client._client = MagicMock()
    client._client.get.side_effect = httpx.ConnectError("refused")

    with patch("cody.client.time.sleep"):
        with pytest.raises(CodyConnectionError, match="after 3 attempts"):
            client.health()

    assert client._client.get.call_count == 3


def test_sync_no_retry_when_disabled():
    """max_retries=0 means no retries"""
    client = CodyClient("http://localhost:8000", max_retries=0)
    client._client = MagicMock()
    client._client.get.side_effect = httpx.ConnectError("refused")

    with pytest.raises(CodyConnectionError, match="after 1 attempts"):
        client.health()

    assert client._client.get.call_count == 1


def test_sync_no_retry_on_non_transient():
    """Don't retry on non-transient errors (e.g., 500)"""
    client = CodyClient("http://localhost:8000", max_retries=3)
    client._client = MagicMock()
    client._client.post.return_value = httpx.Response(
        500, json={"error": {"code": "SERVER_ERROR", "message": "bad"}}
    )

    with pytest.raises(CodyError) as exc_info:
        client.run("test")

    assert exc_info.value.status_code == 500
    # Should only be called once (no retry on server errors)
    assert client._client.post.call_count == 1


# ── Async client retry ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_retry_exhausted():
    """Async client retries and raises after exhaustion"""
    client = AsyncCodyClient("http://localhost:8000", max_retries=1)
    client._client = MagicMock()

    async def mock_get(*args, **kwargs):
        raise httpx.ConnectError("refused")

    client._client.get = mock_get

    with patch("cody.client.asyncio.sleep"):
        with pytest.raises(CodyConnectionError, match="after 2 attempts"):
            await client.health()


@pytest.mark.asyncio
async def test_async_retry_success_on_second():
    """Async client succeeds on second attempt"""
    client = AsyncCodyClient("http://localhost:8000", max_retries=2)
    client._client = MagicMock()

    call_count = 0

    async def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, json={"status": "ok", "version": "0.1.0"})

    client._client.get = mock_get

    with patch("cody.client.asyncio.sleep"):
        result = await client.health()

    assert result["status"] == "ok"
    assert call_count == 2


# ── CodyError fields ───────────────────────────────────────────────────────


def test_cody_error_has_code():
    err = CodyError("test", status_code=400, code="TOOL_ERROR")
    assert err.code == "TOOL_ERROR"
    assert err.status_code == 400
    assert err.message == "test"


def test_cody_not_found_with_code():
    err = CodyNotFoundError("missing", status_code=404, code="SESSION_NOT_FOUND")
    assert err.code == "SESSION_NOT_FOUND"
