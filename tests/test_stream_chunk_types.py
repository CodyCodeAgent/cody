"""Tests for StreamChunk type restructuring (#15)."""

from cody.sdk.types import (
    StreamChunk,
    SessionStartChunk,
    TextDeltaChunk,
    ThinkingChunk,
    ToolCallChunk,
    ToolResultChunk,
    CompactChunk,
    PruneChunk,
    DoneChunk,
    CancelledChunk,
    CircuitBreakerChunk,
    InteractionRequestChunk,
    UserInputReceivedChunk,
    UnknownChunk,
    Usage,
)


# ── Typed chunks are StreamChunk subclasses ──────────────────────────────────


class TestSubclassRelationship:
    def test_text_delta_is_stream_chunk(self):
        chunk = TextDeltaChunk(content="hello")
        assert isinstance(chunk, StreamChunk)
        assert isinstance(chunk, TextDeltaChunk)
        assert chunk.type == "text_delta"
        assert chunk.content == "hello"

    def test_thinking_is_stream_chunk(self):
        chunk = ThinkingChunk(content="reasoning")
        assert isinstance(chunk, StreamChunk)
        assert chunk.type == "thinking"

    def test_tool_call_is_stream_chunk(self):
        chunk = ToolCallChunk(
            content="read_file", tool_name="read_file",
            args={"path": "a.py"}, tool_call_id="tc1",
        )
        assert isinstance(chunk, StreamChunk)
        assert chunk.type == "tool_call"
        assert chunk.tool_name == "read_file"
        assert chunk.args == {"path": "a.py"}
        assert chunk.tool_call_id == "tc1"

    def test_tool_result_is_stream_chunk(self):
        chunk = ToolResultChunk(content="file contents", tool_name="read_file")
        assert isinstance(chunk, StreamChunk)
        assert chunk.type == "tool_result"

    def test_compact_is_stream_chunk(self):
        chunk = CompactChunk(
            original_messages=20, compacted_messages=5,
            estimated_tokens_saved=10000, used_llm=True,
        )
        assert isinstance(chunk, StreamChunk)
        assert chunk.type == "compact"
        assert chunk.original_messages == 20

    def test_done_is_stream_chunk(self):
        chunk = DoneChunk(
            content="result", usage=Usage(100, 50, 150),
            message_history=[{"role": "assistant"}],
        )
        assert isinstance(chunk, StreamChunk)
        assert chunk.type == "done"
        assert chunk.usage.total_tokens == 150

    def test_cancelled_is_stream_chunk(self):
        chunk = CancelledChunk()
        assert isinstance(chunk, StreamChunk)
        assert chunk.type == "cancelled"

    def test_session_start_is_stream_chunk(self):
        chunk = SessionStartChunk(session_id="abc123")
        assert isinstance(chunk, StreamChunk)
        assert chunk.type == "session_start"
        assert chunk.session_id == "abc123"

    def test_circuit_breaker_is_stream_chunk(self):
        chunk = CircuitBreakerChunk(content="cost limit")
        assert isinstance(chunk, StreamChunk)
        assert chunk.type == "circuit_breaker"

    def test_interaction_request_is_stream_chunk(self):
        chunk = InteractionRequestChunk(
            content="Choose an option",
            request_id="req1", interaction_kind="question",
            options=["yes", "no"],
        )
        assert isinstance(chunk, StreamChunk)
        assert chunk.type == "interaction_request"
        assert chunk.options == ["yes", "no"]

    def test_user_input_received_is_stream_chunk(self):
        chunk = UserInputReceivedChunk(content="user said yes")
        assert isinstance(chunk, StreamChunk)
        assert chunk.type == "user_input_received"

    def test_prune_is_stream_chunk(self):
        chunk = PruneChunk(messages_pruned=5, estimated_tokens_saved=3000)
        assert isinstance(chunk, StreamChunk)
        assert chunk.type == "prune"
        assert chunk.messages_pruned == 5
        assert chunk.estimated_tokens_saved == 3000

    def test_unknown_is_stream_chunk(self):
        chunk = UnknownChunk()
        assert isinstance(chunk, StreamChunk)
        assert chunk.type == "unknown"


# ── Backward compatibility ──────────────────────────────────────────────────


class TestBackwardCompat:
    def test_construct_stream_chunk_directly(self):
        """Old code that constructs StreamChunk(type=...) still works."""
        chunk = StreamChunk(type="text_delta", content="hi")
        assert chunk.type == "text_delta"
        assert chunk.content == "hi"
        assert chunk.session_id is None

    def test_all_fields_accessible_on_base(self):
        """All fields accessible on base StreamChunk."""
        chunk = StreamChunk(
            type="tool_call", content="read_file",
            tool_name="read_file", args={"path": "x"},
            tool_call_id="tc1",
        )
        assert chunk.tool_name == "read_file"
        assert chunk.args == {"path": "x"}

    def test_type_string_comparison(self):
        """chunk.type == "..." still works with typed chunks."""
        chunk = TextDeltaChunk(content="hello")
        assert chunk.type == "text_delta"

        chunk2 = ToolCallChunk(tool_name="grep")
        assert chunk2.type == "tool_call"


# ── _event_to_chunk returns typed chunks ────────────────────────────────────


class TestEventConversion:
    def test_text_delta_event(self):
        from cody.core.runner import TextDeltaEvent
        from cody.sdk.types import _event_to_chunk

        event = TextDeltaEvent(content="hello")
        chunk = _event_to_chunk(event, session_id="s1")
        assert isinstance(chunk, TextDeltaChunk)
        assert chunk.content == "hello"
        assert chunk.session_id == "s1"

    def test_tool_call_event(self):
        from cody.core.runner import ToolCallEvent
        from cody.sdk.types import _event_to_chunk

        event = ToolCallEvent(tool_name="grep", args={"q": "x"}, tool_call_id="t1")
        chunk = _event_to_chunk(event)
        assert isinstance(chunk, ToolCallChunk)
        assert chunk.tool_name == "grep"

    def test_cancelled_event(self):
        from cody.core.runner import CancelledEvent
        from cody.sdk.types import _event_to_chunk

        chunk = _event_to_chunk(CancelledEvent())
        assert isinstance(chunk, CancelledChunk)

    def test_session_start_event(self):
        from cody.core.runner import SessionStartEvent
        from cody.sdk.types import _event_to_chunk

        chunk = _event_to_chunk(SessionStartEvent(session_id="s1"), session_id="s1")
        assert isinstance(chunk, SessionStartChunk)
        assert chunk.session_id == "s1"

    def test_prune_event(self):
        from cody.core.runner import PruneEvent
        from cody.sdk.types import _event_to_chunk

        event = PruneEvent(messages_pruned=10, estimated_tokens_saved=5000)
        chunk = _event_to_chunk(event, session_id="s1")
        assert isinstance(chunk, PruneChunk)
        assert chunk.messages_pruned == 10
        assert chunk.estimated_tokens_saved == 5000
        assert chunk.session_id == "s1"

    def test_unknown_event(self):
        from cody.sdk.types import _event_to_chunk

        chunk = _event_to_chunk("totally_unknown_event")
        assert isinstance(chunk, UnknownChunk)


# ── Exports ─────────────────────────────────────────────────────────────────


class TestExports:
    def test_importable_from_sdk(self):
        from cody.sdk import (
            StreamChunk as SC,
            TextDeltaChunk as TDC,
            ToolCallChunk as TCC,
            DoneChunk as DC,
        )
        assert SC is StreamChunk
        assert TDC is TextDeltaChunk
        assert TCC is ToolCallChunk
        assert DC is DoneChunk

    def test_prune_chunk_importable_from_sdk(self):
        from cody.sdk import PruneChunk as PC
        assert PC is PruneChunk

    def test_importable_from_client_shim(self):
        from cody.client import StreamChunk as SC, TextDeltaChunk as TDC, PruneChunk as PC
        assert SC is StreamChunk
        assert TDC is TextDeltaChunk
        assert PC is PruneChunk
