"""Backward-compatible re-exports.

All SDK logic now lives in ``cody.sdk``. This module re-exports the public
symbols so that ``from cody.client import AsyncCodyClient`` continues to work.
"""

from .sdk.client import AsyncCodyClient, CodyClient, Cody  # noqa: F401
from .sdk.errors import (  # noqa: F401
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
from .sdk.types import (  # noqa: F401
    RunResult,
    SessionDetail,
    SessionInfo,
    StreamChunk,
    ToolResult,
    Usage,
)
