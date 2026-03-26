"""Cody agent dependencies - extracted to break circular imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from .interaction import InteractionRequest, InteractionResponse

from .config import Config
from .lsp_client import LSPClient
from .mcp_client import MCPClient
from .permissions import PermissionManager
from .skill_manager import SkillManager
from .storage import AuditLoggerProtocol, FileHistoryProtocol, MemoryStoreProtocol
from .sub_agent import SubAgentManager


class _UnsetType:
    """Sentinel type to distinguish 'not passed' from explicit ``None``.

    Use ``UNSET`` (the singleton instance) as default parameter value
    when ``None`` carries meaning (e.g. "disable this feature").
    """
    _instance: "_UnsetType | None" = None

    def __new__(cls) -> "_UnsetType":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNSET"

    def __bool__(self) -> bool:
        return False


UNSET = _UnsetType()
"""Shared sentinel — use ``is UNSET`` to check."""


# Hook type aliases
if TYPE_CHECKING:
    BeforeToolHook = Callable[[str, dict], Awaitable[dict | None]]
    AfterToolHook = Callable[[str, dict, str], Awaitable[str]]
else:
    BeforeToolHook = Any
    AfterToolHook = Any


class ToolContext:
    """Lightweight RunContext stand-in for direct tool invocation."""
    def __init__(self, deps: 'CodyDeps'):
        self.deps = deps


@dataclass
class CodyDeps:
    """Dependencies for Cody Agent"""
    config: Config
    workdir: Path
    skill_manager: SkillManager
    allowed_roots: list[Path] = field(default_factory=list)
    strict_read_boundary: bool = False
    mcp_client: Optional[MCPClient] = None
    sub_agent_manager: Optional[SubAgentManager] = None
    lsp_client: Optional[LSPClient] = None
    audit_logger: Optional[AuditLoggerProtocol] = None
    permission_manager: Optional[PermissionManager] = None
    file_history: Optional[FileHistoryProtocol] = None
    todo_list: Optional[list] = None
    memory_store: Optional[MemoryStoreProtocol] = None
    interaction_handler: Optional[Callable[[InteractionRequest], Awaitable[InteractionResponse]]] = None
    before_tool_hooks: list[BeforeToolHook] = field(default_factory=list)
    after_tool_hooks: list[AfterToolHook] = field(default_factory=list)
