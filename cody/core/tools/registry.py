"""Tool registry — declarative tool sets and registration functions.

runner.py and sub_agent.py call register_tools() / register_sub_agent_tools()
to batch-register tools on Agent instances.

To add a new tool:
  1. Define the async function in the appropriate module.
  2. Import it here and append to the appropriate *_TOOLS list.
  3. If sub-agents should use it, add to the relevant SUB_AGENT_TOOLSETS.
  That's it — no changes needed in runner.py or sub_agent.py.
"""

from ._base import _with_model_retry
from .file_ops import read_file, write_file, edit_file, list_directory
from .search import grep, glob, patch, search_files
from .command import exec_command
from .skills import list_skills, read_skill
from .agents import spawn_agent, get_agent_status, kill_agent
from .mcp import mcp_list_tools, mcp_call
from .web import webfetch, websearch
from .lsp import lsp_diagnostics, lsp_definition, lsp_references, lsp_hover
from .history import undo_file, redo_file, list_file_changes
from .memory import save_memory
from .todo import todo_write, todo_read
from .user import question

FILE_TOOLS = [read_file, write_file, edit_file, list_directory]
SEARCH_TOOLS = [grep, glob, patch, search_files]
COMMAND_TOOLS = [exec_command]
SKILL_TOOLS = [list_skills, read_skill]
SUB_AGENT_TOOLS = [spawn_agent, get_agent_status, kill_agent]
MCP_TOOLS = [mcp_call, mcp_list_tools]
WEB_TOOLS = [webfetch, websearch]
LSP_TOOLS = [lsp_diagnostics, lsp_definition, lsp_references, lsp_hover]
FILE_HISTORY_TOOLS = [undo_file, redo_file, list_file_changes]
TODO_TOOLS = [todo_write, todo_read]
MEMORY_TOOLS = [save_memory]
USER_TOOLS = [question]

# All tools for the main agent (MCP excluded — conditional on config)
CORE_TOOLS = (
    FILE_TOOLS + SEARCH_TOOLS + COMMAND_TOOLS + SKILL_TOOLS
    + SUB_AGENT_TOOLS + WEB_TOOLS + LSP_TOOLS
    + FILE_HISTORY_TOOLS + TODO_TOOLS + MEMORY_TOOLS + USER_TOOLS
)

# Subsets for sub-agent types.
# "research" is read-only (no write/exec) to prevent side effects.
# "test" can write files and run commands but not spawn further sub-agents.
# "code" and "generic" get the full file+search+command set.
SUB_AGENT_TOOLSETS = {
    "code": FILE_TOOLS + SEARCH_TOOLS + COMMAND_TOOLS,
    "generic": FILE_TOOLS + SEARCH_TOOLS + COMMAND_TOOLS,
    "research": [read_file, list_directory, grep, glob, search_files],
    "test": [read_file, write_file, edit_file, list_directory, grep, glob, exec_command],
}


def register_tools(
    agent,
    *,
    include_mcp: bool = False,
    custom_tools: list | None = None,
) -> None:
    """Register all core tools on an agent. Optionally include MCP tools.

    Each tool is wrapped with _with_model_retry so that ToolError exceptions
    are converted to ModelRetry, allowing the model to self-correct.

    Args:
        agent: Pydantic AI Agent instance.
        include_mcp: Whether to include MCP tools.
        custom_tools: Optional list of user-defined async tool functions.
            Each function must accept ``ctx: RunContext[CodyDeps]`` as
            its first parameter and return ``str``.
    """
    for tool_func in CORE_TOOLS:
        agent.tool(retries=2)(_with_model_retry(tool_func))
    if include_mcp:
        for tool_func in MCP_TOOLS:
            agent.tool(retries=2)(_with_model_retry(tool_func))
    if custom_tools:
        for tool_func in custom_tools:
            agent.tool(retries=2)(_with_model_retry(tool_func))


def register_sub_agent_tools(agent, agent_type: str) -> None:
    """Register the appropriate tool subset for a sub-agent type."""
    tool_set = SUB_AGENT_TOOLSETS.get(agent_type, SUB_AGENT_TOOLSETS["generic"])
    for tool_func in tool_set:
        agent.tool(retries=2)(_with_model_retry(tool_func))
