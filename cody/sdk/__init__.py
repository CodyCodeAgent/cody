"""Cody SDK - Enhanced Python SDK for Cody AI coding assistant.

This module provides a more user-friendly interface to Cody core with:
- Builder pattern for client construction
- Convenience methods for common operations
- Event hooks for monitoring
- Metrics collection
- Better error handling

Usage:
    from cody.sdk import Cody, config
    
    # Method 1: Builder pattern
    client = (
        Cody()
        .workdir("/path/to/project")
        .model("your-model-name")
        .api_key("sk-xxx")
        .thinking(True)
        .build()
    )
    
    # Method 2: Config object
    cfg = config(
        model="your-model-name",
        workdir="/path/to/project",
        api_key="sk-xxx",
        enable_thinking=True,
    )
    client = AsyncCodyClient(config=cfg)
    
    # Method 3: Direct parameters
    async with AsyncCodyClient(
        workdir="/path/to/project",
        model="your-model-name",
    ) as client:
        result = await client.run("Create a hello.py file")
        print(result.output)

Example with events and metrics:
    from cody.sdk import Cody, EventType
    
    client = (
        Cody()
        .workdir("/path/to/project")
        .enable_events()
        .enable_metrics()
        .build()
    )
    
    @client.on(EventType.TOOL_CALL)
    def on_tool(event):
        print(f"Tool called: {event.tool_name}")
    
    async with client:
        result = await client.run("Create a Flask app")
        
        # Get metrics
        metrics = client.get_metrics()
        print(f"Tokens used: {metrics['total_tokens']}")
"""

from .._version import __version__  # noqa: F401

# Core client
from .client import AsyncCodyClient, CodyClient, Cody

# Configuration
from .config import (
    SDKConfig,
    ModelConfig,
    PermissionConfig,
    SecurityConfig,
    MCPConfig,
    LSPConfig,
    config,
)

# Errors
from .errors import (
    CodyError,
    CodyNotFoundError,
    CodyModelError,
    CodyToolError,
    CodyPermissionError,
    CodySessionError,
    CodyRateLimitError,
    CodyConfigError,
    CodyTimeoutError,
    CodyConnectionError,
)

# Response types
from .types import (
    RunResult,
    SessionDetail,
    SessionInfo,
    StreamChunk,
    ToolResult,
    Usage,
)

# Events
from .events import (
    EventManager,
    EventType,
    Event,
    RunEvent,
    ToolEvent,
    ThinkingEvent,
    StreamEvent,
    SessionEvent,
    ModelEvent,
    ContextCompactEvent,
)

# Metrics
from .metrics import (
    MetricsCollector,
    TokenUsage,
    ToolMetrics,
    RunMetrics,
    SessionMetrics,
)

__all__ = [
    # Clients
    "AsyncCodyClient",
    "CodyClient",
    "Cody",
    
    # Config
    "SDKConfig",
    "ModelConfig",
    "PermissionConfig",
    "SecurityConfig",
    "MCPConfig",
    "LSPConfig",
    "config",
    
    # Errors
    "CodyError",
    "CodyNotFoundError",
    "CodyModelError",
    "CodyToolError",
    "CodyPermissionError",
    "CodySessionError",
    "CodyRateLimitError",
    "CodyConfigError",
    "CodyTimeoutError",
    "CodyConnectionError",
    
    # Events
    "EventManager",
    "EventType",
    "Event",
    "RunEvent",
    "ToolEvent",
    "ThinkingEvent",
    "StreamEvent",
    "SessionEvent",
    "ModelEvent",
    "ContextCompactEvent",
    
    # Metrics
    "MetricsCollector",
    "TokenUsage",
    "ToolMetrics",
    "RunMetrics",
    "SessionMetrics",

    # Response types
    "RunResult",
    "SessionDetail",
    "SessionInfo",
    "StreamChunk",
    "ToolResult",
    "Usage",
]
