"""MCP (Model Context Protocol) integration examples for Cody SDK.

Shows how to:
- Configure stdio-based MCP servers (local subprocess)
- Configure HTTP-based MCP servers (remote endpoint)
- Dynamically add MCP servers at runtime
- Directly call MCP tools
"""

import asyncio

from cody.sdk import Cody


# ── Example 1: stdio MCP server (local subprocess) ────────────────────────


async def stdio_mcp_example():
    """Connect to a stdio-based MCP server (e.g. GitHub MCP server)."""
    client = (
        Cody()
        .workdir(".")
        .mcp_stdio_server(
            "github",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_TOKEN": "ghp_your_token_here"},
        )
        .auto_start_mcp(True)  # Start on first run()
        .build()
    )

    async with client:
        result = await client.run("List my recent GitHub pull requests")
        print(result.output)


# ── Example 2: HTTP MCP server (remote endpoint) ──────────────────────────


async def http_mcp_example():
    """Connect to an HTTP-based MCP server (e.g. Feishu/Lark)."""
    client = (
        Cody()
        .workdir(".")
        .mcp_http_server(
            "feishu",
            url="https://mcp.feishu.cn/mcp",
            headers={"X-Lark-MCP-UAT": "your-token-here"},
        )
        .auto_start_mcp(True)
        .build()
    )

    async with client:
        result = await client.run("Summarize the latest Feishu document")
        print(result.output)


# ── Example 3: Multiple MCP servers ───────────────────────────────────────


async def multi_mcp_example():
    """Configure multiple MCP servers simultaneously."""
    client = (
        Cody()
        .workdir(".")
        .mcp_stdio_server(
            "github",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_TOKEN": "ghp_xxx"},
        )
        .mcp_http_server(
            "feishu",
            url="https://mcp.feishu.cn/mcp",
            headers={"X-Lark-MCP-UAT": "your-token"},
        )
        .auto_start_mcp(True)
        .build()
    )

    async with client:
        result = await client.run("List my GitHub PRs and summarize my Feishu docs")
        print(result.output)


# ── Example 4: Dynamic MCP server addition ────────────────────────────────


async def dynamic_mcp_example():
    """Add MCP servers at runtime — useful for conditional tool loading."""
    client = Cody().workdir(".").build()

    async with client:
        # Start with no MCP servers, add one dynamically
        await client.add_mcp_server(
            name="github",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_TOKEN": "ghp_xxx"},
        )

        # HTTP server can also be added dynamically
        await client.add_mcp_server(
            name="feishu",
            transport="http",
            url="https://mcp.feishu.cn/mcp",
            headers={"X-Lark-MCP-UAT": "your-token"},
        )

        # Now the agent has access to both servers
        result = await client.run("What MCP tools are available?")
        print(result.output)


# ── Example 5: Manual MCP start + direct tool calls ──────────────────────


async def manual_mcp_example():
    """Manually start MCP and call tools directly (without agent)."""
    client = (
        Cody()
        .workdir(".")
        .mcp_stdio_server(
            "github",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
        )
        .build()
    )

    async with client:
        # Manually start MCP (useful for controlling startup timing)
        await client.start_mcp()

        # List available MCP tools
        tools = await client.mcp_list_tools()
        print("Available MCP tools:")
        for tool in tools:
            print(f"  - {tool}")

        # Call an MCP tool directly (format: "server_name/tool_name")
        result = await client.mcp_call("github/list-repos", {"per_page": 5})
        print(f"\nDirect call result: {result}")


if __name__ == "__main__":
    asyncio.run(stdio_mcp_example())
