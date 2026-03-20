"""Tests for Python SDK (CodyClient / AsyncCodyClient) — in-process mode"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import asyncio

from cody.core.runner import (
    CancelledEvent, CodyResult, TextDeltaEvent, DoneEvent,
    ToolCallEvent, ToolResultEvent, CompactEvent, ThinkingEvent,
)

from cody.client import (
    AsyncCodyClient,
    CodyClient,
    CodyError,
    CodyNotFoundError,
    RunResult,
    SessionInfo,
    SessionDetail,
)
from cody.sdk.client import _event_to_chunk, _usage_from_result


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_result(output="done", thinking=None):
    """Create a CodyResult with optional mock usage."""
    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_usage.total_tokens = 15
    mock_raw = MagicMock()
    mock_raw.usage.return_value = mock_usage
    mock_raw.all_messages.return_value = []
    return CodyResult(output=output, thinking=thinking, _raw_result=mock_raw)


# ── _event_to_chunk unit tests ───────────────────────────────────────────────


def test_event_to_chunk_text_delta():
    event = TextDeltaEvent(content="hello")
    chunk = _event_to_chunk(event, session_id="s1")
    assert chunk.type == "text_delta"
    assert chunk.content == "hello"
    assert chunk.session_id == "s1"


def test_event_to_chunk_done():
    event = DoneEvent(result=CodyResult(output="all done"))
    chunk = _event_to_chunk(event)
    assert chunk.type == "done"
    assert chunk.content == "all done"
    assert chunk.session_id is None


def test_usage_from_result_with_usage():
    result = _make_result()
    usage = _usage_from_result(result)
    assert usage.input_tokens == 10
    assert usage.output_tokens == 5
    assert usage.total_tokens == 15


def test_usage_from_result_without_usage():
    result = CodyResult(output="no usage")
    usage = _usage_from_result(result)
    assert usage.total_tokens == 0


def test_event_to_chunk_tool_call():
    event = ToolCallEvent(
        tool_name="read_file", args={"path": "test.py"}, tool_call_id="tc_42",
    )
    chunk = _event_to_chunk(event, session_id="s1")
    assert chunk.type == "tool_call"
    assert chunk.tool_name == "read_file"
    assert chunk.args == {"path": "test.py"}
    assert chunk.tool_call_id == "tc_42"
    assert chunk.content == "read_file"
    assert chunk.session_id == "s1"


def test_event_to_chunk_tool_result():
    event = ToolResultEvent(
        tool_name="read_file", tool_call_id="tc_42", result="file contents here",
    )
    chunk = _event_to_chunk(event, session_id="s2")
    assert chunk.type == "tool_result"
    assert chunk.tool_name == "read_file"
    assert chunk.tool_call_id == "tc_42"
    assert chunk.content == "file contents here"
    assert chunk.session_id == "s2"


def test_event_to_chunk_compact():
    event = CompactEvent(
        original_messages=20, compacted_messages=5, estimated_tokens_saved=8000,
    )
    chunk = _event_to_chunk(event)
    assert chunk.type == "compact"
    assert chunk.original_messages == 20
    assert chunk.compacted_messages == 5
    assert chunk.estimated_tokens_saved == 8000


def test_event_to_chunk_thinking():
    event = ThinkingEvent(content="Let me think...")
    chunk = _event_to_chunk(event, session_id="s3")
    assert chunk.type == "thinking"
    assert chunk.content == "Let me think..."
    assert chunk.session_id == "s3"


# ── Async client: start_mcp ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_start_mcp():
    client = AsyncCodyClient()
    mock_runner = MagicMock()
    mock_runner.start_mcp = AsyncMock()

    with patch.object(client, "get_runner", return_value=mock_runner):
        await client.start_mcp()

    mock_runner.start_mcp.assert_awaited_once()
    await client.close()


@pytest.mark.asyncio
async def test_async_stream_with_tool_events():
    """Verify stream() yields StreamChunks with tool_call_id for tool events."""
    client = AsyncCodyClient()

    async def fake_stream_with_session(prompt, store, session_id=None, cancel_event=None):
        sid = session_id or "test-sid"
        yield ToolCallEvent(tool_name="grep", args={"pattern": "foo"}, tool_call_id="tc_1"), sid
        yield ToolResultEvent(tool_name="grep", tool_call_id="tc_1", result="match found"), sid
        yield DoneEvent(result=CodyResult(output="done")), sid

    with patch.object(client, "get_runner") as mock_get_runner, \
         patch.object(client, "get_session_store") as mock_get_store:
        mock_runner = MagicMock()
        mock_runner.run_stream_with_session = fake_stream_with_session
        mock_get_runner.return_value = mock_runner
        mock_get_store.return_value = MagicMock()

        chunks = []
        async for chunk in client.stream("test"):
            chunks.append(chunk)

    tool_call = [c for c in chunks if c.type == "tool_call"][0]
    assert tool_call.tool_name == "grep"
    assert tool_call.tool_call_id == "tc_1"
    assert tool_call.args == {"pattern": "foo"}

    tool_result = [c for c in chunks if c.type == "tool_result"][0]
    assert tool_result.tool_name == "grep"
    assert tool_result.tool_call_id == "tc_1"
    assert tool_result.content == "match found"

    await client.close()


@pytest.mark.asyncio
async def test_async_stream_cancel():
    """Verify cancel_event stops the stream and yields a 'cancelled' chunk."""
    client = AsyncCodyClient()

    async def fake_stream_with_session(prompt, store, session_id=None, cancel_event=None):
        sid = session_id or "test-sid"
        yield TextDeltaEvent(content="Hello"), sid
        # Simulate cancel being set mid-stream
        if cancel_event:
            cancel_event.set()
        yield CancelledEvent(), sid

    with patch.object(client, "get_runner") as mock_get_runner, \
         patch.object(client, "get_session_store") as mock_get_store:
        mock_runner = MagicMock()
        mock_runner.run_stream_with_session = fake_stream_with_session
        mock_get_runner.return_value = mock_runner
        mock_get_store.return_value = MagicMock()

        cancel = asyncio.Event()
        chunks = []
        async for chunk in client.stream("test", cancel_event=cancel):
            chunks.append(chunk)

    types = [c.type for c in chunks]
    assert "text_delta" in types
    assert "cancelled" in types
    # No "done" event should appear after cancel
    assert "done" not in types

    await client.close()


# ── Async client: health ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_health():
    client = AsyncCodyClient()
    result = await client.health()
    assert result["status"] == "ok"
    assert "version" in result
    await client.close()


# ── Async client: run ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_run():
    client = AsyncCodyClient()
    mock_result = _make_result("async result")

    with patch.object(client, "get_runner") as mock_get_runner, \
         patch.object(client, "get_session_store"):
        mock_runner = MagicMock()
        mock_runner.run_with_session = AsyncMock(return_value=(mock_result, "sid123"))
        mock_get_runner.return_value = mock_runner

        result = await client.run("test")

    assert isinstance(result, RunResult)
    assert result.output == "async result"
    assert result.usage.total_tokens == 15
    assert result.session_id == "sid123"
    await client.close()


@pytest.mark.asyncio
async def test_async_run_with_session():
    client = AsyncCodyClient()
    mock_result = _make_result("continued")

    with patch.object(client, "get_runner") as mock_get_runner, \
         patch.object(client, "get_session_store"):
        mock_runner = MagicMock()
        mock_runner.run_with_session = AsyncMock(return_value=(mock_result, "abc123"))
        mock_get_runner.return_value = mock_runner

        result = await client.run("hello", session_id="abc123")

    assert result.session_id == "abc123"
    assert result.output == "continued"
    await client.close()


# ── Async client: stream ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_stream():
    client = AsyncCodyClient()

    async def fake_stream_with_session(prompt, store, session_id=None, cancel_event=None):
        sid = session_id or "test-sid"
        yield TextDeltaEvent(content="Hello"), sid
        yield TextDeltaEvent(content=" async"), sid
        yield DoneEvent(result=CodyResult(output="Hello async")), sid

    with patch.object(client, "get_runner") as mock_get_runner, \
         patch.object(client, "get_session_store") as mock_get_store:
        mock_runner = MagicMock()
        mock_runner.run_stream_with_session = fake_stream_with_session
        mock_get_runner.return_value = mock_runner
        mock_get_store.return_value = MagicMock()

        chunks = []
        async for chunk in client.stream("test"):
            chunks.append(chunk)

    text_chunks = [c for c in chunks if c.type == "text_delta"]
    assert len(text_chunks) == 2
    assert text_chunks[0].content == "Hello"
    assert text_chunks[1].content == " async"

    done_chunks = [c for c in chunks if c.type == "done"]
    assert len(done_chunks) == 1
    assert done_chunks[0].content == "Hello async"
    await client.close()


# ── Async client: tool ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_tool(tmp_path):
    (tmp_path / "hello.py").write_text("print('hi')")
    client = AsyncCodyClient(workdir=str(tmp_path))
    result = await client.tool("read_file", {"path": "hello.py"})
    assert "print('hi')" in result.result
    await client.close()


@pytest.mark.asyncio
async def test_async_tool_not_found():
    client = AsyncCodyClient()
    with pytest.raises(CodyNotFoundError):
        await client.tool("nonexistent_tool")
    await client.close()


# ── Async client: sessions ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_session_lifecycle(tmp_path):
    client = AsyncCodyClient(db_path=str(tmp_path / "test.db"))

    session = await client.create_session(title="test session")
    assert isinstance(session, SessionInfo)
    assert session.title == "test session"

    sessions = await client.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].id == session.id

    detail = await client.get_session(session.id)
    assert isinstance(detail, SessionDetail)
    assert detail.messages == []

    await client.delete_session(session.id)
    with pytest.raises(CodyNotFoundError):
        await client.get_session(session.id)

    await client.close()


@pytest.mark.asyncio
async def test_async_session_not_found(tmp_path):
    client = AsyncCodyClient(db_path=str(tmp_path / "test.db"))
    with pytest.raises(CodyNotFoundError, match="Session not found"):
        await client.get_session("nonexistent")
    await client.close()


@pytest.mark.asyncio
async def test_async_delete_session_not_found(tmp_path):
    client = AsyncCodyClient(db_path=str(tmp_path / "test.db"))
    with pytest.raises(CodyNotFoundError):
        await client.delete_session("nonexistent")
    await client.close()


# ── Async client: skills ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_list_skills():
    client = AsyncCodyClient()
    skills = await client.list_skills()
    assert isinstance(skills, list)
    names = [s["name"] for s in skills]
    assert "git" in names
    await client.close()


@pytest.mark.asyncio
async def test_async_get_skill():
    client = AsyncCodyClient()
    skill = await client.get_skill("git")
    assert skill["name"] == "git"
    assert "documentation" in skill
    assert len(skill["documentation"]) > 0
    await client.close()


@pytest.mark.asyncio
async def test_async_get_skill_not_found():
    client = AsyncCodyClient()
    with pytest.raises(CodyNotFoundError):
        await client.get_skill("nonexistent_skill_xyz")
    await client.close()


# ── Sync client ──────────────────────────────────────────────────────────────


def test_sync_health():
    client = CodyClient()
    result = client.health()
    assert result["status"] == "ok"
    client.close()


def test_sync_session_lifecycle(tmp_path):
    client = CodyClient(db_path=str(tmp_path / "test.db"))

    session = client.create_session(title="sync session")
    assert session.title == "sync session"

    sessions = client.list_sessions()
    assert len(sessions) == 1

    detail = client.get_session(session.id)
    assert detail.messages == []

    client.delete_session(session.id)
    with pytest.raises(CodyNotFoundError):
        client.get_session(session.id)

    client.close()


def test_sync_tool(tmp_path):
    (tmp_path / "test.txt").write_text("hello world")
    client = CodyClient(workdir=str(tmp_path))
    result = client.tool("read_file", {"path": "test.txt"})
    assert "hello world" in result.result
    client.close()


def test_sync_tool_not_found():
    client = CodyClient()
    with pytest.raises(CodyNotFoundError):
        client.tool("nonexistent_tool")
    client.close()


# ── Error classes ─────────────────────────────────────────────────────────────


def test_cody_error_fields():
    err = CodyError("test", status_code=400, code="TOOL_ERROR")
    assert err.code == "TOOL_ERROR"
    assert err.status_code == 400
    assert err.message == "test"


def test_cody_not_found_is_cody_error():
    err = CodyNotFoundError("missing", code="SESSION_NOT_FOUND")
    assert isinstance(err, CodyError)
    assert err.code == "SESSION_NOT_FOUND"
