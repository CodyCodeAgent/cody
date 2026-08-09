"""Start the repository's deterministic stdio MCP server and call it directly."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

from cody.sdk import Cody


async def run() -> None:
    root = Path(__file__).resolve().parents[1]
    server = root / "scripts" / "live_mcp_server.py"
    client = (
        Cody()
        .workdir(str(root))
        .mcp_stdio_server("demo", command=sys.executable, args=[str(server)])
        .build()
    )
    async with client:
        await client.start_mcp()
        tools = await client.mcp_list_tools()
        result = await client.mcp_call("demo/echo_marker", {"value": "hello"})
        print("Tools:", [tool["name"] for tool in tools])
        print("Result:", result)


if __name__ == "__main__":
    asyncio.run(run())
