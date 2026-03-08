"""Core tools for Cody Agent — split into submodules by category.

Every tool has the same signature:
    async def tool_name(ctx: RunContext[CodyDeps], ...) -> str

Tools are grouped into categorized lists in registry.py
(FILE_TOOLS, SEARCH_TOOLS, etc.). runner.py and sub_agent.py call
register_tools() / register_sub_agent_tools() instead of hard-coding
individual agent.tool() calls — adding a new tool is one list edit.

Error conventions:
  - ToolInvalidParams  → bad arguments          (server maps to 400)
  - ToolPathDenied     → path outside workdir    (server maps to 403)
  - ToolPermissionDenied → permission check fail (server maps to 403)
  - FileNotFoundError  → missing file/dir        (server maps to 500)

In agent context, all ToolError subclasses are automatically converted to
pydantic-ai ModelRetry (via _with_model_retry wrapper in register_tools),
so the model can self-correct and retry instead of breaking the run.
"""

# Re-export all public tools for backward compatibility
from .file_ops import read_file, write_file, edit_file, list_directory
from .search import grep, glob, patch, search_files
from .command import exec_command
from .skills import list_skills, read_skill
from .agents import spawn_agent, get_agent_status, kill_agent
from .mcp import mcp_list_tools, mcp_call
from .web import webfetch, websearch
from .lsp import lsp_diagnostics, lsp_definition, lsp_references, lsp_hover
from .history import undo_file, redo_file, list_file_changes
from .todo import todo_write, todo_read
from .user import question

# Re-export registry
from .registry import (
    FILE_TOOLS, SEARCH_TOOLS, COMMAND_TOOLS, SKILL_TOOLS,
    SUB_AGENT_TOOLS, MCP_TOOLS, WEB_TOOLS, LSP_TOOLS,
    FILE_HISTORY_TOOLS, TODO_TOOLS, USER_TOOLS,
    CORE_TOOLS, SUB_AGENT_TOOLSETS,
    register_tools, register_sub_agent_tools,
)

__all__ = [
    # Tool functions
    "read_file", "write_file", "edit_file", "list_directory",
    "grep", "glob", "patch", "search_files",
    "exec_command",
    "list_skills", "read_skill",
    "spawn_agent", "get_agent_status", "kill_agent",
    "mcp_list_tools", "mcp_call",
    "webfetch", "websearch",
    "lsp_diagnostics", "lsp_definition", "lsp_references", "lsp_hover",
    "undo_file", "redo_file", "list_file_changes",
    "todo_write", "todo_read",
    "question",
    # Tool lists
    "FILE_TOOLS", "SEARCH_TOOLS", "COMMAND_TOOLS", "SKILL_TOOLS",
    "SUB_AGENT_TOOLS", "MCP_TOOLS", "WEB_TOOLS", "LSP_TOOLS",
    "FILE_HISTORY_TOOLS", "TODO_TOOLS", "USER_TOOLS",
    "CORE_TOOLS", "SUB_AGENT_TOOLSETS",
    # Registration
    "register_tools", "register_sub_agent_tools",
]
