"""Cody agent dependencies - extracted to break circular imports."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .audit import AuditLogger
from .config import Config
from .file_history import FileHistory
from .lsp_client import LSPClient
from .mcp_client import MCPClient
from .memory import ProjectMemoryStore
from .permissions import PermissionManager
from .skill_manager import SkillManager
from .sub_agent import SubAgentManager


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
    audit_logger: Optional[AuditLogger] = None
    permission_manager: Optional[PermissionManager] = None
    file_history: Optional[FileHistory] = None
    todo_list: Optional[list] = None
    memory_store: Optional[ProjectMemoryStore] = None
    # Callback for human-in-the-loop interaction.
    # Set by AgentRunner when interaction is enabled.
    # Signature: (InteractionRequest) -> Awaitable[InteractionResponse]
    interaction_handler: Optional[object] = None
