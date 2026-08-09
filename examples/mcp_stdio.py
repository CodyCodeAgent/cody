"""Start the repository's deterministic stdio MCP server and call it directly."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

from cody.core.config import MCPConfig, MCPServerConfig
from cody.core.mcp_client import MCPClient


async def run() -> None:
    root = Path(__file__).resolve().parents[1]
    server = root / "scripts" / "live_mcp_server.py"
    config = MCPConfig(
        servers=[
            MCPServerConfig(
                name="demo",
                command=sys.executable,
                args=[str(server)],
            )
        ]
    )
    async with MCPClient(config) as client:
        failures = await client.start_all()
        if failures:
            raise RuntimeError("; ".join(failures))
        tools = client.list_tools()
        result = await client.call_tool("demo/echo_marker", {"value": "hello"})
        print("Tools:", [tool.name for tool in tools])
        print("Result:", result)


if __name__ == "__main__":
    asyncio.run(run())
