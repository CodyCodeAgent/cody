"""MCP (Model Context Protocol) Client integration.

Manages MCP server processes and exposes their tools to the Cody Agent.
Each MCP server runs as a subprocess communicating over stdio using JSON-RPC.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .config import MCPConfig, MCPServerConfig

logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    """A tool exposed by an MCP server."""
    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str


@dataclass
class _ServerProcess:
    """Internal: tracks a running MCP server subprocess."""
    config: MCPServerConfig
    process: Optional[asyncio.subprocess.Process] = None
    tools: list[MCPTool] = field(default_factory=list)
    _request_id: int = 0
    _pending: dict[int, asyncio.Future] = field(default_factory=dict)
    _reader_task: Optional[asyncio.Task] = None

    def next_id(self) -> int:
        self._request_id += 1
        return self._request_id


class MCPClient:
    """Manage MCP server lifecycles and proxy tool calls.

    Usage:
        mcp = MCPClient(config.mcp)
        await mcp.start_all()
        tools = mcp.list_tools()
        result = await mcp.call_tool("server/tool_name", {...})
        await mcp.stop_all()
    """

    def __init__(self, config: MCPConfig):
        self.config = config
        self._servers: dict[str, _ServerProcess] = {}

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start_all(self) -> None:
        """Start all configured MCP servers."""
        for server_cfg in self.config.servers:
            try:
                await self.start_server(server_cfg)
            except Exception as e:
                logger.error("Failed to start MCP server %s: %s", server_cfg.name, e)

    async def start_server(self, cfg: MCPServerConfig) -> None:
        """Start a single MCP server subprocess."""
        env = dict(cfg.env) if cfg.env else None

        process = await asyncio.create_subprocess_exec(
            cfg.command, *cfg.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        sp = _ServerProcess(config=cfg, process=process)
        self._servers[cfg.name] = sp

        # Start background reader for responses
        sp._reader_task = asyncio.create_task(self._reader_loop(cfg.name))

        # Initialize the server
        await self._send_initialize(cfg.name)

        # Discover tools
        await self._discover_tools(cfg.name)

        logger.info(
            "MCP server '%s' started (pid=%s, tools=%d)",
            cfg.name, process.pid, len(sp.tools),
        )

    async def stop_all(self) -> None:
        """Stop all running MCP servers."""
        for name in list(self._servers):
            await self.stop_server(name)

    async def stop_server(self, name: str) -> None:
        """Stop a single MCP server."""
        sp = self._servers.pop(name, None)
        if sp is None:
            return

        if sp._reader_task and not sp._reader_task.done():
            sp._reader_task.cancel()
            try:
                await sp._reader_task
            except asyncio.CancelledError:
                pass

        if sp.process and sp.process.returncode is None:
            sp.process.terminate()
            try:
                await asyncio.wait_for(sp.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                sp.process.kill()
                await sp.process.wait()

        logger.info("MCP server '%s' stopped", name)

    async def restart_server(self, name: str) -> None:
        """Restart a server (stop + start)."""
        sp = self._servers.get(name)
        if sp is None:
            raise ValueError(f"Unknown MCP server: {name}")
        cfg = sp.config
        await self.stop_server(name)
        await self.start_server(cfg)

    # ── Tool discovery & invocation ──────────────────────────────────────────

    def list_tools(self) -> list[MCPTool]:
        """Return all tools from all running servers."""
        result: list[MCPTool] = []
        for sp in self._servers.values():
            result.extend(sp.tools)
        return result

    def get_tool(self, qualified_name: str) -> Optional[MCPTool]:
        """Get a tool by 'server_name/tool_name'."""
        for sp in self._servers.values():
            for tool in sp.tools:
                if f"{sp.config.name}/{tool.name}" == qualified_name:
                    return tool
        return None

    async def call_tool(
        self,
        qualified_name: str,
        arguments: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Call an MCP tool by 'server_name/tool_name'."""
        parts = qualified_name.split("/", 1)
        if len(parts) != 2:
            raise ValueError(
                f"Invalid tool name '{qualified_name}'. Expected 'server/tool'."
            )
        server_name, tool_name = parts

        sp = self._servers.get(server_name)
        if sp is None:
            raise ValueError(f"MCP server not running: {server_name}")

        result = await self._jsonrpc_call(
            server_name,
            "tools/call",
            {"name": tool_name, "arguments": arguments or {}},
        )

        # MCP call result is {content: [{type: "text", text: "..."}], isError: bool}
        if isinstance(result, dict):
            if result.get("isError"):
                content_parts = result.get("content", [])
                err_msg = " ".join(
                    p.get("text", "") for p in content_parts if p.get("type") == "text"
                )
                raise RuntimeError(f"MCP tool error: {err_msg}")
            content_parts = result.get("content", [])
            texts = [
                p.get("text", "") for p in content_parts if p.get("type") == "text"
            ]
            return "\n".join(texts) if texts else str(result)

        return result

    # ── JSON-RPC transport ───────────────────────────────────────────────────

    async def _jsonrpc_call(
        self,
        server_name: str,
        method: str,
        params: Optional[dict] = None,
    ) -> Any:
        """Send JSON-RPC request and wait for response."""
        sp = self._servers.get(server_name)
        if sp is None or sp.process is None:
            raise RuntimeError(f"MCP server '{server_name}' is not running")

        req_id = sp.next_id()
        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        sp._pending[req_id] = future

        line = json.dumps(request) + "\n"
        try:
            sp.process.stdin.write(line.encode())
            await sp.process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            sp._pending.pop(req_id, None)
            raise RuntimeError(
                f"MCP server '{server_name}' process died: {e}"
            ) from e

        try:
            result = await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            sp._pending.pop(req_id, None)
            raise RuntimeError(
                f"MCP call '{method}' to '{server_name}' timed out after 30s"
            )

        return result

    async def _reader_loop(self, server_name: str) -> None:
        """Read JSON-RPC responses from stdout."""
        sp = self._servers.get(server_name)
        if sp is None or sp.process is None:
            return

        try:
            while True:
                line = await sp.process.stdout.readline()
                if not line:
                    break

                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                req_id = msg.get("id")
                if req_id is not None and req_id in sp._pending:
                    future = sp._pending.pop(req_id)
                    if "error" in msg:
                        future.set_exception(
                            RuntimeError(
                                f"MCP error: {msg['error'].get('message', msg['error'])}"
                            )
                        )
                    else:
                        future.set_result(msg.get("result"))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("MCP reader loop error for '%s': %s", server_name, e)

    async def _send_initialize(self, server_name: str) -> None:
        """Send MCP initialize handshake."""
        await self._jsonrpc_call(
            server_name,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "cody", "version": "1.1.1"},
            },
        )
        # Send initialized notification (no id, no response expected)
        sp = self._servers[server_name]
        if sp.process and sp.process.stdin:
            notification = json.dumps({
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }) + "\n"
            sp.process.stdin.write(notification.encode())
            await sp.process.stdin.drain()

    async def _discover_tools(self, server_name: str) -> None:
        """Discover tools from an MCP server."""
        result = await self._jsonrpc_call(server_name, "tools/list", {})

        sp = self._servers[server_name]
        sp.tools = []

        if isinstance(result, dict) and "tools" in result:
            for t in result["tools"]:
                sp.tools.append(MCPTool(
                    name=t["name"],
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", {}),
                    server_name=server_name,
                ))

    # ── Context manager ─────────────────────────────────────────────────────

    async def __aenter__(self):
        await self.start_all()
        return self

    async def __aexit__(self, *args):
        await self.stop_all()

    @property
    def running_servers(self) -> list[str]:
        """Names of currently running servers."""
        return list(self._servers.keys())
