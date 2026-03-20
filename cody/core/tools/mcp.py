"""MCP (Model Context Protocol) tools."""

from pydantic_ai import RunContext

from ..deps import CodyDeps
from ._base import _check_permission


async def mcp_list_tools(ctx: RunContext['CodyDeps']) -> str:
    """List tools from connected MCP servers"""
    client = ctx.deps.mcp_client
    if client is None:
        return "No MCP servers configured"

    mcp_tools = client.list_tools()
    if not mcp_tools:
        return "No MCP tools available"

    lines = ["MCP tools:"]
    for t in mcp_tools:
        lines.append(f"  {t.server_name}/{t.name} — {t.description}")

    return "\n".join(lines)


async def mcp_call(
    ctx: RunContext['CodyDeps'],
    tool_name: str,
    arguments: str = "{}",
) -> str:
    """Call an MCP tool by qualified name (server/tool)

    Args:
        tool_name: Qualified tool name, e.g. "github/create_issue"
        arguments: JSON string of tool arguments
    """
    await _check_permission(ctx, "mcp_call")
    import json as _json

    client = ctx.deps.mcp_client
    if client is None:
        return "[ERROR] No MCP servers configured"

    try:
        args = _json.loads(arguments) if arguments else {}
    except _json.JSONDecodeError as e:
        return f"[ERROR] Invalid JSON arguments: {e}"

    try:
        result = await client.call_tool(tool_name, args)
        return str(result)
    except Exception as e:
        return f"[ERROR] MCP call failed: {e}"
