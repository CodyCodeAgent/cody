"""Tests for WebSocket API"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from cody.core.runner import (
    CodyResult, CompactEvent, ThinkingEvent, TextDeltaEvent,
    ToolCallEvent, ToolResultEvent, DoneEvent, ToolTrace,
)
from web.backend.helpers import serialize_stream_event as _serialize_stream_event
from web.backend.app import app


# ── _serialize_stream_event unit tests ─────────────────────────────────────


def test_serialize_compact_event():
    """CompactEvent serialises with compaction details."""
    event = CompactEvent(
        original_messages=42,
        compacted_messages=5,
        estimated_tokens_saved=85000,
    )
    result = _serialize_stream_event(event)
    assert result["type"] == "compact"
    assert result["original_messages"] == 42
    assert result["compacted_messages"] == 5
    assert result["estimated_tokens_saved"] == 85000


def test_serialize_thinking_event():
    """ThinkingEvent serialises with type and content."""
    event = ThinkingEvent(content="hmm...")
    result = _serialize_stream_event(event)
    assert result == {"type": "thinking", "content": "hmm..."}


def test_serialize_text_delta_event():
    """TextDeltaEvent serialises with type and content."""
    event = TextDeltaEvent(content="Hello")
    result = _serialize_stream_event(event)
    assert result == {"type": "text_delta", "content": "Hello"}


def test_serialize_tool_call_event():
    """ToolCallEvent includes tool_name, args, tool_call_id."""
    event = ToolCallEvent(
        tool_name="read_file",
        args={"path": "/tmp/x.py"},
        tool_call_id="tc_1",
    )
    result = _serialize_stream_event(event)
    assert result["type"] == "tool_call"
    assert result["tool_name"] == "read_file"
    assert result["args"] == {"path": "/tmp/x.py"}
    assert result["tool_call_id"] == "tc_1"


def test_serialize_tool_result_event():
    """ToolResultEvent includes tool_name, tool_call_id, truncated result."""
    event = ToolResultEvent(
        tool_name="read_file",
        tool_call_id="tc_1",
        result="x" * 600,
    )
    result = _serialize_stream_event(event)
    assert result["type"] == "tool_result"
    assert result["tool_name"] == "read_file"
    assert result["tool_call_id"] == "tc_1"
    assert len(result["result"]) == 500  # truncated


def test_serialize_done_event_minimal():
    """DoneEvent with no traces and no usage."""
    event = DoneEvent(result=CodyResult(output="done", thinking="let me think"))
    result = _serialize_stream_event(event)
    assert result["type"] == "done"
    assert result["output"] == "done"
    assert result["thinking"] == "let me think"
    assert "tool_traces" not in result
    assert "usage" not in result


def test_serialize_done_event_with_traces():
    """DoneEvent serialises tool_traces (truncated result)."""
    traces = [ToolTrace(tool_name="grep", args={"q": "foo"}, result="y" * 600)]
    event = DoneEvent(result=CodyResult(output="ok", tool_traces=traces))
    result = _serialize_stream_event(event)
    assert len(result["tool_traces"]) == 1
    assert result["tool_traces"][0]["tool_name"] == "grep"
    assert len(result["tool_traces"][0]["result"]) == 500


def test_serialize_done_event_with_usage():
    """DoneEvent includes usage when raw_result has it."""
    mock_usage = MagicMock()
    mock_usage.total_tokens = 42
    mock_raw = MagicMock()
    mock_raw.usage.return_value = mock_usage
    mock_raw.all_messages.return_value = []
    event = DoneEvent(result=CodyResult(output="ok", _raw_result=mock_raw))
    result = _serialize_stream_event(event)
    assert result["usage"] == {"total_tokens": 42}


def test_serialize_with_session_id():
    """session_id is injected into every event type."""
    event = TextDeltaEvent(content="hi")
    result = _serialize_stream_event(event, session_id="s-123")
    assert result["session_id"] == "s-123"


def test_serialize_without_session_id():
    """session_id is absent when not provided."""
    event = TextDeltaEvent(content="hi")
    result = _serialize_stream_event(event)
    assert "session_id" not in result


# ── Basic WebSocket protocol ────────────────────────────────────────────────


def test_ws_ping_pong():
    """WebSocket ping/pong"""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "ping"})
        data = ws.receive_json()
        assert data["type"] == "pong"


def test_ws_unknown_message():
    """Unknown message type returns error"""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "unknown_thing"})
        data = ws.receive_json()
        assert data["type"] == "error"
        assert data["error"]["code"] == "INVALID_PARAMS"
        assert "unknown_thing" in data["error"]["message"].lower()


# ── Run via WebSocket ───────────────────────────────────────────────────────


def test_ws_run_missing_prompt():
    """Run without prompt returns error"""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "run", "data": {}})
        data = ws.receive_json()
        assert data["type"] == "error"
        assert data["error"]["code"] == "INVALID_PARAMS"
        assert "prompt" in data["error"]["message"]


def test_ws_run_stream():
    """Run via WebSocket with streaming"""
    async def fake_stream(prompt, message_history=None):
        yield TextDeltaEvent(content="Hello")
        yield TextDeltaEvent(content=" WS")
        yield DoneEvent(result=CodyResult(output="Hello WS"))

    with patch("web.backend.routes.websocket.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run_stream = fake_stream

        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({
                "type": "run",
                "data": {"prompt": "test ws"},
            })

            # Should receive: start, text_delta, text_delta, done
            events = []
            for _ in range(4):
                events.append(ws.receive_json())

            types = [e["type"] for e in events]
            assert "start" in types
            assert "text_delta" in types
            assert "done" in types

            # Check text chunks
            text_events = [e for e in events if e["type"] == "text_delta"]
            contents = [e["content"] for e in text_events]
            assert "Hello" in contents
            assert " WS" in contents


def test_ws_run_stream_with_thinking_and_tools():
    """Full event mix: thinking, tool_call, tool_result, text_delta, done."""
    async def rich_stream(prompt, message_history=None):
        yield ThinkingEvent(content="Let me check...")
        yield ToolCallEvent(tool_name="grep", args={"q": "foo"}, tool_call_id="tc_1")
        yield ToolResultEvent(tool_name="grep", tool_call_id="tc_1", result="found it")
        yield TextDeltaEvent(content="Result: found")
        yield DoneEvent(result=CodyResult(output="Result: found", thinking="Let me check..."))

    with patch("web.backend.routes.websocket.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run_stream = rich_stream

        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "run", "data": {"prompt": "search"}})

            # start + thinking + tool_call + tool_result + text_delta + done = 6
            events = []
            for _ in range(6):
                events.append(ws.receive_json())

            types = [e["type"] for e in events]
            assert types[0] == "start"
            assert "thinking" in types
            assert "tool_call" in types
            assert "tool_result" in types
            assert "text_delta" in types
            assert types[-1] == "done"

            # Verify thinking content
            thinking = [e for e in events if e["type"] == "thinking"]
            assert thinking[0]["content"] == "Let me check..."

            # Verify tool_call fields
            tc = [e for e in events if e["type"] == "tool_call"][0]
            assert tc["tool_name"] == "grep"
            assert tc["args"] == {"q": "foo"}
            assert tc["tool_call_id"] == "tc_1"

            # Verify tool_result fields
            tr = [e for e in events if e["type"] == "tool_result"][0]
            assert tr["tool_name"] == "grep"
            assert tr["result"] == "found it"

            # Verify done carries output + thinking
            done = [e for e in events if e["type"] == "done"][0]
            assert done["output"] == "Result: found"
            assert done["thinking"] == "Let me check..."


def test_ws_run_with_session_id():
    """Run with session_id uses run_stream_with_session path."""
    async def fake_session_stream(prompt, store, session_id):
        yield TextDeltaEvent(content="hi"), "sess-42"
        yield DoneEvent(result=CodyResult(output="hi")), "sess-42"

    with patch("web.backend.routes.websocket.AgentRunner") as MockRunner, \
         patch("web.backend.routes.websocket.get_session_store"):
        instance = MockRunner.return_value
        instance.run_stream_with_session = fake_session_stream

        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({
                "type": "run",
                "data": {"prompt": "hello", "session_id": "sess-42"},
            })

            # start + text_delta + done = 3
            events = []
            for _ in range(3):
                events.append(ws.receive_json())

            types = [e["type"] for e in events]
            assert types[0] == "start"
            assert "text_delta" in types
            assert "done" in types

            # session_id should be in the start event
            assert events[0].get("session_id") == "sess-42"

            # session_id should propagate through stream events
            text_ev = [e for e in events if e["type"] == "text_delta"][0]
            assert text_ev.get("session_id") == "sess-42"


def test_ws_run_error():
    """Run via WebSocket handles errors"""
    async def failing_stream(prompt, message_history=None):
        raise RuntimeError("ws error")
        yield

    with patch("web.backend.routes.websocket.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run_stream = failing_stream

        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({
                "type": "run",
                "data": {"prompt": "test"},
            })

            # Start event
            start = ws.receive_json()
            assert start["type"] == "start"

            # Error event
            error = ws.receive_json()
            assert error["type"] == "error"
            assert "ws error" in error["error"]["message"]


def test_ws_run_error_mid_stream():
    """Error raised mid-stream after some events have been sent."""
    async def mid_error_stream(prompt, message_history=None):
        yield TextDeltaEvent(content="partial")
        raise RuntimeError("mid-stream boom")
        yield  # noqa: F841

    with patch("web.backend.routes.websocket.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run_stream = mid_error_stream

        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "run", "data": {"prompt": "test"}})

            # start + text_delta + error = 3
            events = []
            for _ in range(3):
                events.append(ws.receive_json())

            types = [e["type"] for e in events]
            assert types[0] == "start"
            assert "text_delta" in types
            assert types[-1] == "error"
            assert "mid-stream boom" in events[-1]["error"]["message"]


# ── Cancel ──────────────────────────────────────────────────────────────────


def test_ws_cancel_without_running():
    """Cancel when nothing is running"""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "cancel"})
        data = ws.receive_json()
        assert data["type"] == "cancelled"


# ── Multiple messages ───────────────────────────────────────────────────────


def test_ws_multiple_pings():
    """Multiple ping/pong in same connection"""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        for _ in range(3):
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"


def test_ws_run_then_ping():
    """Connection stays usable after a run completes."""
    async def quick_stream(prompt, message_history=None):
        yield TextDeltaEvent(content="ok")
        yield DoneEvent(result=CodyResult(output="ok"))

    with patch("web.backend.routes.websocket.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run_stream = quick_stream

        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            # First: run
            ws.send_json({"type": "run", "data": {"prompt": "go"}})
            for _ in range(3):  # start + text_delta + done
                ws.receive_json()

            # Then: ping should still work
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"
