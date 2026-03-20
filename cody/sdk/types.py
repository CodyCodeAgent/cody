"""SDK response types and stream event conversion.

These data classes are the public response types returned by CodyClient /
AsyncCodyClient.  The two helper functions convert core-layer objects into
SDK-layer objects.
"""

from dataclasses import dataclass, field
from typing import Optional

from ..core.runner import (
    CancelledEvent,
    CodyResult,
    CompactEvent,
    DoneEvent,
    SessionStartEvent,
    StreamEvent as CoreStreamEvent,
    TextDeltaEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)


# ── Response types ───────────────────────────────────────────────────────────


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class RunResult:
    output: str
    session_id: Optional[str] = None
    usage: Usage = field(default_factory=Usage)
    thinking: Optional[str] = None


@dataclass
class StreamChunk:
    type: str  # "session_start", "text_delta", "thinking", "tool_call", "tool_result", "done", "compact", "cancelled"
    content: str = ""
    session_id: Optional[str] = None
    # Tool call details (populated when type="tool_call")
    tool_name: Optional[str] = None
    args: Optional[dict] = None
    # Tool call ID (populated when type="tool_call" or "tool_result")
    tool_call_id: Optional[str] = None
    # Usage info (populated when type="done")
    usage: Optional[Usage] = None
    # Compact event details (populated when type="compact")
    original_messages: int = 0
    compacted_messages: int = 0
    estimated_tokens_saved: int = 0
    used_llm: bool = False
    # Message history (populated when type="done") for multi-turn state
    message_history: Optional[list] = None


@dataclass
class SessionInfo:
    id: str
    title: str
    model: str
    workdir: str
    message_count: int
    created_at: str
    updated_at: str


@dataclass
class SessionDetail(SessionInfo):
    messages: list[dict] = field(default_factory=list)


@dataclass
class ToolResult:
    result: str


# ── Conversion helpers ───────────────────────────────────────────────────────


def _event_to_chunk(
    event: CoreStreamEvent, session_id: Optional[str] = None
) -> StreamChunk:
    """Convert a core StreamEvent to an SDK StreamChunk."""
    if isinstance(event, TextDeltaEvent):
        return StreamChunk(type="text_delta", content=event.content, session_id=session_id)
    elif isinstance(event, ThinkingEvent):
        return StreamChunk(type="thinking", content=event.content, session_id=session_id)
    elif isinstance(event, ToolCallEvent):
        return StreamChunk(
            type="tool_call", content=event.tool_name, session_id=session_id,
            tool_name=event.tool_name, args=event.args,
            tool_call_id=event.tool_call_id,
        )
    elif isinstance(event, ToolResultEvent):
        return StreamChunk(
            type="tool_result", content=event.result, session_id=session_id,
            tool_name=event.tool_name,
            tool_call_id=event.tool_call_id,
        )
    elif isinstance(event, CompactEvent):
        return StreamChunk(
            type="compact", session_id=session_id,
            original_messages=event.original_messages,
            compacted_messages=event.compacted_messages,
            estimated_tokens_saved=event.estimated_tokens_saved,
            used_llm=event.used_llm,
        )
    elif isinstance(event, DoneEvent):
        return StreamChunk(
            type="done", content=event.result.output, session_id=session_id,
            usage=_usage_from_result(event.result),
            message_history=event.result.all_messages(),
        )
    elif isinstance(event, CancelledEvent):
        return StreamChunk(type="cancelled", session_id=session_id)
    elif isinstance(event, SessionStartEvent):
        return StreamChunk(type="session_start", session_id=session_id)
    return StreamChunk(type="unknown", session_id=session_id)


def _usage_from_result(result: CodyResult) -> Usage:
    """Extract Usage from a CodyResult."""
    raw = result.usage()
    if raw is None:
        return Usage()
    input_t = getattr(raw, "input_tokens", 0) or 0
    output_t = getattr(raw, "output_tokens", 0) or 0
    total_t = getattr(raw, "total_tokens", 0)
    if not total_t:
        total_t = input_t + output_t
    return Usage(input_tokens=input_t, output_tokens=output_t, total_tokens=total_t)
