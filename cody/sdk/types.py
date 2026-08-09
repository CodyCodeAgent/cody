"""SDK response types and stream event conversion.

These data classes are the public response types returned by CodyClient /
AsyncCodyClient.  The two helper functions convert core-layer objects into
SDK-layer objects.

StreamChunk is a discriminated union of typed chunk dataclasses.  Each chunk
type carries only the fields relevant to it.  Consumers can use isinstance()
for type-safe narrowing or check ``chunk.type`` for compatibility with
existing code.
"""

from dataclasses import dataclass, field
from typing import Optional

from ..core.runner import (
    CancelledEvent,
    CircuitBreakerEvent,
    CodyResult,
    CompactEvent,
    DoneEvent,
    InteractionRequestEvent,
    PruneEvent,
    RetryEvent,
    SessionStartEvent,
    StreamEvent as CoreStreamEvent,
    TaskMetadata,
    TextDeltaEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
    UserInputReceivedEvent,
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
    run_id: Optional[str] = None
    usage: Usage = field(default_factory=Usage)
    thinking: Optional[str] = None
    metadata: Optional[TaskMetadata] = None


# ── StreamChunk base class + typed subclasses ────────────────────────────────
#
# ``StreamChunk`` is the base dataclass (backward compatible — can be
# constructed directly).  Typed subclasses allow ``isinstance()`` narrowing
# for type-safe consumers.


@dataclass
class StreamChunk:
    """A single chunk from a streaming response.

    This is the base class that carries all possible fields.  For type-safe
    code, use ``isinstance()`` with the specific chunk subclasses (e.g.
    ``TextDeltaChunk``, ``ToolCallChunk``).
    """
    type: str
    content: str = ""
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    # Tool call details (populated when type="tool_call")
    tool_name: Optional[str] = None
    args: Optional[dict] = None
    # Tool call ID (populated when type="tool_call" or "tool_result")
    tool_call_id: Optional[str] = None
    # Usage info (populated when type="done")
    usage: Optional[Usage] = None
    # Compact/prune event details
    original_messages: int = 0
    compacted_messages: int = 0
    estimated_tokens_saved: int = 0
    used_llm: bool = False
    messages_pruned: int = 0
    # Message history (populated when type="done") for multi-turn state
    message_history: Optional[list] = None
    # Interaction request details (populated when type="interaction_request")
    request_id: Optional[str] = None
    interaction_kind: Optional[str] = None
    options: Optional[list[str]] = None
    # Retry details (populated when type="retry")
    retry_attempt: Optional[int] = None
    retry_max_attempts: Optional[int] = None


# ── Typed subclasses for isinstance() narrowing ─────────────────────────────


@dataclass
class SessionStartChunk(StreamChunk):
    """Emitted at the start of a stream with the session ID."""
    type: str = "session_start"


@dataclass
class TextDeltaChunk(StreamChunk):
    """Incremental text from the model."""
    type: str = "text_delta"


@dataclass
class ThinkingChunk(StreamChunk):
    """Model thinking/reasoning content."""
    type: str = "thinking"


@dataclass
class ToolCallChunk(StreamChunk):
    """A tool invocation by the model."""
    type: str = "tool_call"


@dataclass
class ToolResultChunk(StreamChunk):
    """Result from a tool execution."""
    type: str = "tool_result"


@dataclass
class CompactChunk(StreamChunk):
    """Context compaction event."""
    type: str = "compact"


@dataclass
class PruneChunk(StreamChunk):
    """Tool output pruning event."""
    type: str = "prune"


@dataclass
class DoneChunk(StreamChunk):
    """Stream completion with final output and usage."""
    type: str = "done"


@dataclass
class CancelledChunk(StreamChunk):
    """Stream was cancelled."""
    type: str = "cancelled"


@dataclass
class RetryChunk(StreamChunk):
    """About to retry a failed LLM call (clear buffered partial output)."""
    type: str = "retry"


@dataclass
class CircuitBreakerChunk(StreamChunk):
    """Circuit breaker triggered."""
    type: str = "circuit_breaker"


@dataclass
class InteractionRequestChunk(StreamChunk):
    """The model is requesting human input."""
    type: str = "interaction_request"


@dataclass
class UserInputReceivedChunk(StreamChunk):
    """User input was received during interaction."""
    type: str = "user_input_received"


@dataclass
class UnknownChunk(StreamChunk):
    """Fallback for unrecognized event types."""
    type: str = "unknown"


# ── Other response types ────────────────────────────────────────────────────


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
        return TextDeltaChunk(content=event.content, session_id=session_id)
    elif isinstance(event, ThinkingEvent):
        return ThinkingChunk(content=event.content, session_id=session_id)
    elif isinstance(event, ToolCallEvent):
        return ToolCallChunk(
            content=event.tool_name, session_id=session_id,
            tool_name=event.tool_name, args=event.args,
            tool_call_id=event.tool_call_id,
        )
    elif isinstance(event, ToolResultEvent):
        return ToolResultChunk(
            content=event.result, session_id=session_id,
            tool_name=event.tool_name,
            tool_call_id=event.tool_call_id,
        )
    elif isinstance(event, CompactEvent):
        return CompactChunk(
            session_id=session_id,
            original_messages=event.original_messages,
            compacted_messages=event.compacted_messages,
            estimated_tokens_saved=event.estimated_tokens_saved,
            used_llm=event.used_llm,
        )
    elif isinstance(event, PruneEvent):
        return PruneChunk(
            session_id=session_id,
            messages_pruned=event.messages_pruned,
            estimated_tokens_saved=event.estimated_tokens_saved,
        )
    elif isinstance(event, DoneEvent):
        return DoneChunk(
            content=event.result.output, session_id=session_id,
            usage=_usage_from_result(event.result),
            message_history=event.result.all_messages(),
        )
    elif isinstance(event, CancelledEvent):
        return CancelledChunk(session_id=session_id)
    elif isinstance(event, RetryEvent):
        return RetryChunk(
            content=event.error,
            session_id=session_id,
            retry_attempt=event.attempt,
            retry_max_attempts=event.max_attempts,
        )
    elif isinstance(event, SessionStartEvent):
        return SessionStartChunk(session_id=session_id)
    elif isinstance(event, CircuitBreakerEvent):
        return CircuitBreakerChunk(
            content=f"Circuit breaker: {event.reason} (tokens={event.tokens_used}, cost=${event.cost_usd:.4f})",
            session_id=session_id,
        )
    elif isinstance(event, InteractionRequestEvent):
        return InteractionRequestChunk(
            content=event.request.prompt,
            session_id=session_id,
            request_id=event.request.id,
            interaction_kind=event.request.kind,
            options=event.request.options or None,
        )
    elif isinstance(event, UserInputReceivedEvent):
        return UserInputReceivedChunk(
            content=event.content,
            session_id=session_id,
        )
    return UnknownChunk(session_id=session_id)


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


def _runtime_event_to_chunk(
    event,
    session_id: Optional[str] = None,
    model_result: Optional[CodyResult] = None,
) -> Optional[StreamChunk]:
    """Convert a persisted canonical RunEvent into the legacy SDK stream shape."""

    from ..core.runtime.events import RunEventType

    payload = event.payload
    common = {"session_id": session_id, "run_id": event.run_id}
    event_type = event.event_type
    if event_type == RunEventType.SESSION_STARTED:
        return SessionStartChunk(
            session_id=str(payload.get("session_id") or session_id or ""),
            run_id=event.run_id,
        )
    if event_type == RunEventType.MODEL_TEXT_DELTA:
        return TextDeltaChunk(content=str(payload.get("content") or ""), **common)
    if event_type == RunEventType.MODEL_THINKING_DELTA:
        return ThinkingChunk(content=str(payload.get("content") or ""), **common)
    if event_type == RunEventType.TOOL_CALL_STARTED:
        name = str(payload.get("tool_name") or "")
        return ToolCallChunk(
            content=name,
            tool_name=name,
            args=payload.get("args") or {},
            tool_call_id=payload.get("tool_call_id"),
            **common,
        )
    if event_type == RunEventType.TOOL_CALL_COMPLETED:
        return ToolResultChunk(
            content=str(payload.get("result") or ""),
            tool_name=str(payload.get("tool_name") or ""),
            tool_call_id=payload.get("tool_call_id"),
            **common,
        )
    if event_type == RunEventType.CONTEXT_COMPACTED:
        return CompactChunk(
            original_messages=int(payload.get("original_messages") or 0),
            compacted_messages=int(payload.get("compacted_messages") or 0),
            estimated_tokens_saved=int(payload.get("estimated_tokens_saved") or 0),
            used_llm=bool(payload.get("used_llm")),
            **common,
        )
    if event_type == RunEventType.CONTEXT_PRUNED:
        return PruneChunk(
            messages_pruned=int(payload.get("messages_pruned") or 0),
            estimated_tokens_saved=int(payload.get("estimated_tokens_saved") or 0),
            **common,
        )
    if event_type == RunEventType.MODEL_RETRYING:
        return RetryChunk(
            content=str(payload.get("error") or ""),
            retry_attempt=int(payload.get("attempt") or 0),
            retry_max_attempts=int(payload.get("max_attempts") or 0),
            **common,
        )
    if event_type == RunEventType.CIRCUIT_BREAKER_TRIGGERED:
        reason = str(payload.get("reason") or "")
        tokens = int(payload.get("tokens_used") or 0)
        cost = float(payload.get("cost_usd") or 0)
        return CircuitBreakerChunk(
            content=f"Circuit breaker: {reason} (tokens={tokens}, cost=${cost:.4f})",
            **common,
        )
    if event_type == RunEventType.HUMAN_INPUT_REQUESTED:
        request = payload.get("request") or {}
        return InteractionRequestChunk(
            content=str(request.get("prompt") or ""),
            # Canonical Runtime interactions are addressed by their durable
            # approval id. Legacy transient events may still carry request.id.
            request_id=payload.get("approval_id") or request.get("id"),
            interaction_kind=request.get("kind"),
            options=request.get("options") or None,
            **common,
        )
    if event_type == RunEventType.USER_INPUT_RECEIVED:
        return UserInputReceivedChunk(content=str(payload.get("content") or ""), **common)
    if event_type == RunEventType.RUN_CANCELLED:
        return CancelledChunk(**common)
    if event_type == RunEventType.RUN_COMPLETED:
        usage = _usage_from_result(model_result) if model_result is not None else Usage(
            input_tokens=int((payload.get("usage") or {}).get("input_tokens") or 0),
            output_tokens=int((payload.get("usage") or {}).get("output_tokens") or 0),
            total_tokens=int((payload.get("usage") or {}).get("total_tokens") or 0),
        )
        return DoneChunk(
            content=str(payload.get("output") or ""),
            usage=usage,
            message_history=(model_result.all_messages() if model_result is not None else None),
            **common,
        )
    return None
