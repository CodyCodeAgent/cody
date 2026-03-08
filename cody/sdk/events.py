"""Cody SDK - Event system.

Provides event hooks for monitoring SDK operations.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class EventType(str, Enum):
    """Event types for SDK hooks."""
    
    # Run events
    RUN_START = "run_start"
    RUN_END = "run_end"
    RUN_ERROR = "run_error"
    
    # Stream events
    STREAM_START = "stream_start"
    STREAM_CHUNK = "stream_chunk"
    STREAM_END = "stream_end"
    
    # Tool events
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"
    
    # Thinking events
    THINKING_START = "thinking_start"
    THINKING_CHUNK = "thinking_chunk"
    THINKING_END = "thinking_end"
    
    # Session events
    SESSION_CREATE = "session_create"
    SESSION_CLOSE = "session_close"
    
    # Model events
    MODEL_REQUEST = "model_request"
    MODEL_RESPONSE = "model_response"
    MODEL_ERROR = "model_error"
    
    # Context events
    CONTEXT_COMPACT = "context_compact"


@dataclass
class Event:
    """Base event class."""
    
    event_type: EventType
    timestamp: float = field(default_factory=time.time)
    data: dict = field(default_factory=dict)


@dataclass
class RunEvent(Event):
    """Run event with prompt and result."""
    prompt: str = ""
    session_id: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ToolEvent(Event):
    """Tool call event."""
    tool_name: str = ""
    args: dict = field(default_factory=dict)
    result: Optional[str] = None
    error: Optional[str] = None
    duration: float = 0.0


@dataclass
class ThinkingEvent(Event):
    """Thinking event."""
    content: str = ""
    is_start: bool = False
    is_end: bool = False


@dataclass
class StreamEvent(Event):
    """Stream chunk event."""
    chunk_type: str = ""
    content: str = ""


@dataclass
class SessionEvent(Event):
    """Session event."""
    session_id: str = ""
    title: str = ""


@dataclass
class ModelEvent(Event):
    """Model API event."""
    model: str = ""
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    error: Optional[str] = None


@dataclass
class ContextCompactEvent(Event):
    """Context compaction event."""
    original_messages: int = 0
    compacted_messages: int = 0
    tokens_saved: int = 0


# Type alias for event handlers
EventHandler = Callable[[Event], None]
AsyncEventHandler = Callable[[Event], Any]


class EventManager:
    """Manages event subscriptions and dispatching.
    
    Usage:
        events = EventManager()
        
        @events.on(EventType.TOOL_CALL)
        def on_tool_call(event: ToolEvent):
            print(f"Tool called: {event.tool_name}")
        
        @events.on_async(EventType.RUN_END)
        async def on_run_end(event: RunEvent):
            await log_to_database(event)
        
        # Fire event
        events.dispatch(ToolEvent(
            event_type=EventType.TOOL_CALL,
            tool_name="read_file",
            args={"path": "main.py"},
        ))
    """
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._handlers: dict[EventType, list[EventHandler]] = {}
        self._async_handlers: dict[EventType, list[AsyncEventHandler]] = {}
        self._logger = logging.getLogger(__name__)
    
    def on(self, event_type: EventType) -> Callable[[EventHandler], EventHandler]:
        """Register synchronous event handler (decorator).
        
        Usage:
            @events.on(EventType.TOOL_CALL)
            def handler(event):
                print(f"Tool: {event.tool_name}")
        """
        def decorator(handler: EventHandler) -> EventHandler:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)
            return handler
        return decorator
    
    def on_async(self, event_type: EventType) -> Callable[[AsyncEventHandler], AsyncEventHandler]:
        """Register asynchronous event handler (decorator).
        
        Usage:
            @events.on_async(EventType.RUN_END)
            async def handler(event):
                await save_to_db(event)
        """
        def decorator(handler: AsyncEventHandler) -> AsyncEventHandler:
            if event_type not in self._async_handlers:
                self._async_handlers[event_type] = []
            self._async_handlers[event_type].append(handler)
            return handler
        return decorator
    
    def register(self, event_type: EventType, handler: EventHandler) -> None:
        """Register synchronous event handler."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
    
    def register_async(self, event_type: EventType, handler: AsyncEventHandler) -> None:
        """Register asynchronous event handler."""
        if event_type not in self._async_handlers:
            self._async_handlers[event_type] = []
        self._async_handlers[event_type].append(handler)
    
    def unregister(self, event_type: EventType, handler: EventHandler) -> None:
        """Unregister event handler."""
        if event_type in self._handlers:
            self._handlers[event_type].remove(handler)
    
    def dispatch(self, event: Event) -> None:
        """Dispatch event to all registered handlers (sync)."""
        if not self.enabled:
            return
        
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                self._logger.error(f"Event handler error: {e}", exc_info=True)
    
    async def dispatch_async(self, event: Event) -> None:
        """Dispatch event to all registered handlers (async)."""
        if not self.enabled:
            return
        
        # Sync handlers
        self.dispatch(event)
        
        # Async handlers
        handlers = self._async_handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                self._logger.error(f"Async event handler error: {e}", exc_info=True)
    
    def clear(self) -> None:
        """Clear all event handlers."""
        self._handlers.clear()
        self._async_handlers.clear()


# Pre-built event handlers for common use cases

def create_logging_handler(level: int = logging.INFO) -> EventHandler:
    """Create a logging event handler.
    
    Usage:
        events.register(EventType.TOOL_CALL, create_logging_handler())
    """
    logger = logging.getLogger("cody.sdk.events")
    
    def handler(event: Event):
        logger.log(level, f"[{event.event_type.value}] {event.data}")
    
    return handler


def create_print_handler() -> EventHandler:
    """Create a simple print event handler.
    
    Usage:
        events.register(EventType.TOOL_CALL, create_print_handler())
    """
    def handler(event: Event):
        print(f"📡 Event: {event.event_type.value}")
        if isinstance(event, ToolEvent):
            print(f"   Tool: {event.tool_name}")
        elif isinstance(event, ThinkingEvent):
            print(f"   Thinking: {event.content[:50]}...")
    
    return handler


def create_collector_handler(
    maxlen: int | None = None,
) -> tuple[EventHandler, list[Event]]:
    """Create an event collector for testing/debugging.

    Args:
        maxlen: Optional maximum number of events to retain. When set,
            uses a collections.deque that automatically discards the
            oldest events when full. Default None = unlimited list.

    Returns:
        Tuple of (handler, collected_events_container)

    Usage:
        handler, events = create_collector_handler()
        event_manager.register(EventType.TOOL_CALL, handler)
        # ... run operations ...
        print(f"Collected {len(events)} events")
    """
    collected: list[Event] = []
    if maxlen is not None:
        from collections import deque
        collected = deque(maxlen=maxlen)  # type: ignore[assignment]

    def handler(event: Event) -> None:
        collected.append(event)

    return handler, collected
