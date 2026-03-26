"""Tests for serialize_stream_event helper."""

from unittest.mock import MagicMock

from cody.core.runner import (
    CodyResult, CompactEvent, ThinkingEvent, TextDeltaEvent,
    ToolCallEvent, ToolResultEvent, DoneEvent, ToolTrace,
)
from web.backend.helpers import serialize_stream_event as _serialize_stream_event


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
