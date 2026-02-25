"""Tests for Python SDK (CodyClient / AsyncCodyClient)"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from cody.client import (
    AsyncCodyClient,
    CodyClient,
    CodyConnectionError,
    CodyError,
    CodyNotFoundError,
    RunResult,
    SessionInfo,
    SessionDetail,
    ToolResult,
)
from cody.server import app


# ── Helpers ──────────────────────────────────────────────────────────────────


def _async_client() -> AsyncCodyClient:
    """Create an async CodyClient backed by the real FastAPI app (no network)."""
    transport = httpx.ASGITransport(app=app)
    client = AsyncCodyClient.__new__(AsyncCodyClient)
    client.base_url = "http://testserver"
    client.max_retries = 0
    client._client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    return client


def _mock_response(status_code: int = 200, json_data: dict = None) -> httpx.Response:
    """Build a mock httpx.Response."""
    return httpx.Response(
        status_code=status_code,
        json=json_data or {},
    )


# ── Sync client: unit tests (mocked HTTP) ───────────────────────────────────


def test_sync_health():
    client = CodyClient("http://localhost:8000")
    client._client = MagicMock()
    client._client.get.return_value = _mock_response(200, {"status": "ok", "version": "0.1.0"})

    result = client.health()
    assert result["status"] == "ok"
    client._client.get.assert_called_once_with("/health")


def test_sync_run():
    client = CodyClient("http://localhost:8000")
    client._client = MagicMock()
    client._client.post.return_value = _mock_response(200, {
        "status": "success",
        "output": "done",
        "session_id": None,
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    })

    result = client.run("hello")
    assert isinstance(result, RunResult)
    assert result.output == "done"
    assert result.usage.total_tokens == 15
    assert result.session_id is None


def test_sync_run_with_session():
    client = CodyClient("http://localhost:8000")
    client._client = MagicMock()
    client._client.post.return_value = _mock_response(200, {
        "status": "success",
        "output": "continued",
        "session_id": "abc123",
        "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    })

    result = client.run("hello", session_id="abc123")
    assert result.session_id == "abc123"
    # Verify session_id was sent in request body
    call_args = client._client.post.call_args
    body = call_args.kwargs["json"]
    assert body["session_id"] == "abc123"


def test_sync_run_with_options():
    client = CodyClient("http://localhost:8000")
    client._client = MagicMock()
    client._client.post.return_value = _mock_response(200, {
        "status": "success",
        "output": "done",
        "session_id": None,
        "usage": {},
    })

    client.run("hello", workdir="/tmp/test", model="openai:gpt-4o")
    body = client._client.post.call_args.kwargs["json"]
    assert body["prompt"] == "hello"
    assert body["workdir"] == "/tmp/test"
    assert body["model"] == "openai:gpt-4o"


def test_sync_tool():
    client = CodyClient("http://localhost:8000")
    client._client = MagicMock()
    client._client.post.return_value = _mock_response(200, {
        "status": "success",
        "result": "file contents here",
    })

    result = client.tool("read_file", {"path": "test.txt"}, workdir="/tmp")
    assert isinstance(result, ToolResult)
    assert result.result == "file contents here"
    body = client._client.post.call_args.kwargs["json"]
    assert body["tool"] == "read_file"
    assert body["params"] == {"path": "test.txt"}
    assert body["workdir"] == "/tmp"


def test_sync_create_session():
    client = CodyClient("http://localhost:8000")
    client._client = MagicMock()
    client._client.post.return_value = _mock_response(200, {
        "id": "abc123def456",
        "title": "my session",
        "model": "test",
        "workdir": "/tmp",
        "message_count": 0,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    })

    session = client.create_session(title="my session")
    assert isinstance(session, SessionInfo)
    assert session.id == "abc123def456"
    assert session.title == "my session"


def test_sync_list_sessions():
    client = CodyClient("http://localhost:8000")
    client._client = MagicMock()
    client._client.get.return_value = _mock_response(200, {
        "sessions": [
            {
                "id": "s1", "title": "first", "model": "", "workdir": "",
                "message_count": 2, "created_at": "2026-01-01", "updated_at": "2026-01-01",
            },
            {
                "id": "s2", "title": "second", "model": "", "workdir": "",
                "message_count": 0, "created_at": "2026-01-01", "updated_at": "2026-01-01",
            },
        ]
    })

    sessions = client.list_sessions()
    assert len(sessions) == 2
    assert sessions[0].id == "s1"
    assert sessions[1].title == "second"


def test_sync_get_session():
    client = CodyClient("http://localhost:8000")
    client._client = MagicMock()
    client._client.get.return_value = _mock_response(200, {
        "id": "s1", "title": "chat", "model": "", "workdir": "",
        "message_count": 2, "created_at": "2026-01-01", "updated_at": "2026-01-01",
        "messages": [
            {"role": "user", "content": "hello", "timestamp": "2026-01-01"},
            {"role": "assistant", "content": "hi", "timestamp": "2026-01-01"},
        ],
    })

    detail = client.get_session("s1")
    assert isinstance(detail, SessionDetail)
    assert len(detail.messages) == 2
    assert detail.messages[0]["role"] == "user"


def test_sync_delete_session():
    client = CodyClient("http://localhost:8000")
    client._client = MagicMock()
    client._client.delete.return_value = _mock_response(200, {"status": "deleted", "id": "s1"})

    client.delete_session("s1")  # should not raise
    client._client.delete.assert_called_once_with("/sessions/s1")


# ── Sync client: error handling ──────────────────────────────────────────────


def test_sync_connection_error():
    client = CodyClient("http://localhost:99999")
    with pytest.raises(CodyConnectionError):
        client.health()
    client.close()


def test_sync_404_raises_not_found():
    client = CodyClient("http://localhost:8000")
    client._client = MagicMock()
    client._client.get.return_value = _mock_response(404, {"detail": "Session not found: xyz"})

    with pytest.raises(CodyNotFoundError, match="Session not found"):
        client.get_session("xyz")


def test_sync_500_raises_cody_error():
    client = CodyClient("http://localhost:8000")
    client._client = MagicMock()
    client._client.post.return_value = _mock_response(500, {"detail": "Internal error"})

    with pytest.raises(CodyError) as exc_info:
        client.run("test")
    assert exc_info.value.status_code == 500


# ── Async client: integration tests (real FastAPI) ───────────────────────────


@pytest.mark.asyncio
async def test_async_health():
    client = _async_client()
    result = await client.health()
    assert result["status"] == "ok"
    await client.close()


@pytest.mark.asyncio
async def test_async_run():
    mock_result = MagicMock()
    mock_result.output = "async result"
    mock_usage = MagicMock()
    mock_usage.input_tokens = 20
    mock_usage.output_tokens = 10
    mock_usage.total_tokens = 30
    mock_result.usage.return_value = mock_usage

    with patch("cody.server.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = AsyncMock(return_value=mock_result)

        client = _async_client()
        result = await client.run("test")

    assert isinstance(result, RunResult)
    assert result.output == "async result"
    assert result.usage.total_tokens == 30
    await client.close()


@pytest.mark.asyncio
async def test_async_tool(tmp_path):
    (tmp_path / "hello.py").write_text("print('hi')")
    client = _async_client()
    result = await client.tool("read_file", {"path": "hello.py"}, workdir=str(tmp_path))
    assert "print('hi')" in result.result
    await client.close()


@pytest.mark.asyncio
async def test_async_tool_not_found():
    client = _async_client()
    with pytest.raises(CodyNotFoundError):
        await client.tool("nonexistent_tool")
    await client.close()


@pytest.mark.asyncio
async def test_async_session_lifecycle(tmp_path):
    from cody.core.session import SessionStore
    store = SessionStore(db_path=tmp_path / "test.db")

    with patch("cody.server._get_session_store", return_value=store):
        client = _async_client()

        session = await client.create_session(title="async test")
        assert session.title == "async test"

        sessions = await client.list_sessions()
        assert len(sessions) == 1

        detail = await client.get_session(session.id)
        assert detail.messages == []

        await client.delete_session(session.id)
        with pytest.raises(CodyNotFoundError):
            await client.get_session(session.id)

        await client.close()


@pytest.mark.asyncio
async def test_async_list_skills():
    client = _async_client()
    skills = await client.list_skills()
    assert isinstance(skills, list)
    names = [s["name"] for s in skills]
    assert "git" in names
    await client.close()


@pytest.mark.asyncio
async def test_async_get_skill():
    client = _async_client()
    skill = await client.get_skill("git")
    assert skill["name"] == "git"
    assert "documentation" in skill
    assert len(skill["documentation"]) > 0
    await client.close()


@pytest.mark.asyncio
async def test_async_get_skill_not_found():
    client = _async_client()
    with pytest.raises(CodyNotFoundError):
        await client.get_skill("nonexistent_skill_xyz")
    await client.close()


@pytest.mark.asyncio
async def test_async_stream():
    async def fake_stream(prompt, message_history=None):
        for chunk in ["Hello", " async"]:
            yield chunk

    with patch("cody.server.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run_stream = fake_stream

        client = _async_client()
        chunks = []
        async for chunk in client.stream("test"):
            chunks.append(chunk)

    text_chunks = [c for c in chunks if c.type == "text"]
    assert len(text_chunks) == 2
    assert text_chunks[0].content == "Hello"
    assert text_chunks[1].content == " async"
    await client.close()
