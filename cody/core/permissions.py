"""Tool-level permission system"""

from enum import Enum
from typing import Optional


class PermissionLevel(str, Enum):
    """Permission levels for tools."""
    ALLOW = "allow"
    DENY = "deny"
    CONFIRM = "confirm"


# Default permissions: read-only tools are allowed, mutating tools need confirmation
_DEFAULT_PERMISSIONS: dict[str, PermissionLevel] = {
    # Read-only — always allowed
    "read_file": PermissionLevel.ALLOW,
    "list_directory": PermissionLevel.ALLOW,
    "grep": PermissionLevel.ALLOW,
    "glob": PermissionLevel.ALLOW,
    "search_files": PermissionLevel.ALLOW,
    "list_skills": PermissionLevel.ALLOW,
    "read_skill": PermissionLevel.ALLOW,
    "get_agent_status": PermissionLevel.ALLOW,
    "mcp_list_tools": PermissionLevel.ALLOW,
    "lsp_diagnostics": PermissionLevel.ALLOW,
    "lsp_definition": PermissionLevel.ALLOW,
    "lsp_references": PermissionLevel.ALLOW,
    "lsp_hover": PermissionLevel.ALLOW,
    "websearch": PermissionLevel.ALLOW,
    "webfetch": PermissionLevel.ALLOW,
    "list_file_changes": PermissionLevel.ALLOW,
    "todo_read": PermissionLevel.ALLOW,
    "todo_write": PermissionLevel.ALLOW,
    "question": PermissionLevel.ALLOW,
    # Mutating — require confirmation
    "write_file": PermissionLevel.CONFIRM,
    "edit_file": PermissionLevel.CONFIRM,
    "patch": PermissionLevel.CONFIRM,
    "exec_command": PermissionLevel.CONFIRM,
    "spawn_agent": PermissionLevel.CONFIRM,
    "kill_agent": PermissionLevel.CONFIRM,
    "mcp_call": PermissionLevel.CONFIRM,
    "undo_file": PermissionLevel.CONFIRM,
    "redo_file": PermissionLevel.CONFIRM,
}


class PermissionDeniedError(Exception):
    """Raised when a tool call is denied by the permission system."""

    def __init__(self, tool_name: str, reason: str = ""):
        self.tool_name = tool_name
        self.reason = reason or f"Permission denied for tool: {tool_name}"
        super().__init__(self.reason)


class PermissionManager:
    """Manages tool-level permissions."""

    def __init__(
        self,
        overrides: Optional[dict[str, str]] = None,
        default_level: PermissionLevel = PermissionLevel.CONFIRM,
    ):
        self._overrides: dict[str, PermissionLevel] = {}
        if overrides:
            for tool_name, level_str in overrides.items():
                self._overrides[tool_name] = PermissionLevel(level_str)
        self._default_level = default_level

    def get_level(self, tool_name: str) -> PermissionLevel:
        """Get the effective permission level for a tool."""
        # User overrides take highest priority
        if tool_name in self._overrides:
            return self._overrides[tool_name]
        # Then built-in defaults
        if tool_name in _DEFAULT_PERMISSIONS:
            return _DEFAULT_PERMISSIONS[tool_name]
        # Unknown tools get the default level
        return self._default_level

    def check(self, tool_name: str) -> PermissionLevel:
        """Check permission for a tool call.

        Returns the permission level. Raises PermissionDeniedError if denied.

        Note on CONFIRM level: this method returns PermissionLevel.CONFIRM without
        raising an exception. The CONFIRM level passes through silently at the core
        layer — actual confirmation UX (prompting the user, blocking until answered,
        etc.) is entirely the responsibility of the caller (CLI, TUI, or Web frontend).
        Core never blocks on user input.
        """
        level = self.get_level(tool_name)
        if level == PermissionLevel.DENY:
            raise PermissionDeniedError(tool_name)
        return level

    def set_override(self, tool_name: str, level: PermissionLevel) -> None:
        """Set a permission override for a tool."""
        self._overrides[tool_name] = level

    def remove_override(self, tool_name: str) -> None:
        """Remove a permission override."""
        self._overrides.pop(tool_name, None)

    def list_permissions(self) -> dict[str, str]:
        """List effective permissions for all known tools."""
        all_tools = set(_DEFAULT_PERMISSIONS.keys()) | set(self._overrides.keys())
        return {tool: self.get_level(tool).value for tool in sorted(all_tools)}
