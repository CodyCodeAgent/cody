"""MCP (Model Context Protocol) Client integration.

Manages MCP server connections and exposes their tools to the Cody Agent.
Supports two transport modes:
- stdio: subprocess communicating over stdin/stdout using JSON-RPC.
- http: JSON-RPC over HTTP POST (e.g. Feishu MCP, remote MCP servers).
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from .config import MCPConfig, MCPServerConfig
from .._version import __version__ as _version

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
    """Internal: tracks a running MCP server subprocess (stdio transport)."""
    config: MCPServerConfig
    process: Optional[asyncio.subprocess.Process] = None
    tools: list[MCPTool] = field(default_factory=list)
    _request_id: int = 0
    _pending: dict[int, asyncio.Future] = field(default_factory=dict)
    _reader_task: Optional[asyncio.Task] = None

    def next_id(self) -> int:
        self._request_id += 1
        return self._request_id


@dataclass
class _HttpConnection:
    """Internal: tracks an HTTP-based MCP server connection."""
    config: MCPServerConfig
    client: Optional[httpx.AsyncClient] = None
    tools: list[MCPTool] = field(default_factory=list)
    _request_id: int = 0

    def next_id(self) -> int:
        self._request_id += 1
        return self._request_id


class MCPClient:
    """Manage MCP server lifecycles and proxy tool calls.

    Supports both stdio (subprocess) and HTTP transport modes.

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
        self._http_servers: dict[str, _HttpConnection] = {}

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start_all(self) -> list[str]:
        """Start all configured MCP servers. Returns list of failure messages."""
        failures: list[str] = []
        for server_cfg in self.config.servers:
            try:
                await self.start_server(server_cfg)
            except Exception as e:
                msg = f"MCP server '{server_cfg.name}' failed to start: {e}"
                logger.error(msg)
                failures.append(msg)
        return failures

    async def start_server(self, cfg: MCPServerConfig) -> None:
        """Start a single MCP server (stdio subprocess or HTTP connection)."""
        if cfg.transport == 'http':
            await self._start_http_server(cfg)
        else:
            await self._start_stdio_server(cfg)

    async def _start_stdio_server(self, cfg: MCPServerConfig) -> None:
        """Start a stdio-based MCP server subprocess."""
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

        try:
            await self._send_initialize_stdio(cfg.name)
            await self._discover_tools_stdio(cfg.name)
        except Exception:
            orphan = self._servers.pop(cfg.name, None)
            if orphan:
                if orphan._reader_task and not orphan._reader_task.done():
                    orphan._reader_task.cancel()
                if orphan.process and orphan.process.returncode is None:
                    orphan.process.kill()
            raise

        logger.info(
            "MCP server '%s' started (stdio, pid=%s, tools=%d)",
            cfg.name, process.pid, len(sp.tools),
        )

    async def _start_http_server(self, cfg: MCPServerConfig) -> None:
        """Connect to an HTTP-based MCP server."""
        if not cfg.url:
            raise ValueError(f"MCP server '{cfg.name}': HTTP transport requires 'url'")

        client = httpx.AsyncClient(timeout=30.0)
        conn = _HttpConnection(config=cfg, client=client)
        self._http_servers[cfg.name] = conn

        try:
            await self._send_initialize_http(cfg.name)
            await self._discover_tools_http(cfg.name)
        except Exception:
            self._http_servers.pop(cfg.name, None)
            await client.aclose()
            raise

        logger.info(
            "MCP server '%s' connected (http, url=%s, tools=%d)",
            cfg.name, cfg.url, len(conn.tools),
        )

    async def stop_all(self) -> None:
        """Stop all running MCP servers."""
        for name in list(self._servers):
            await self.stop_server(name)
        for name in list(self._http_servers):
            await self.stop_server(name)

    async def stop_server(self, name: str) -> None:
        """Stop a single MCP server."""
        # Try stdio first
        sp = self._servers.pop(name, None)
        if sp is not None:
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
            return

        # Try HTTP
        conn = self._http_servers.pop(name, None)
        if conn is not None:
            if conn.client:
                await conn.client.aclose()
            logger.info("MCP server '%s' disconnected", name)

    async def restart_server(self, name: str) -> None:
        """Restart a server (stop + start)."""
        sp = self._servers.get(name)
        conn = self._http_servers.get(name)
        if sp is None and conn is None:
            raise ValueError(f"Unknown MCP server: {name}")
        cfg = sp.config if sp else conn.config  # type: ignore[union-attr]
        await self.stop_server(name)
        await self.start_server(cfg)

    # ── Tool discovery & invocation ──────────────────────────────────────────

    def list_tools(self) -> list[MCPTool]:
        """Return all tools from all running servers."""
        result: list[MCPTool] = []
        for sp in self._servers.values():
            result.extend(sp.tools)
        for conn in self._http_servers.values():
            result.extend(conn.tools)
        return result

    def get_tool(self, qualified_name: str) -> Optional[MCPTool]:
        """Get a tool by 'server_name/tool_name'."""
        for sp in self._servers.values():
            for tool in sp.tools:
                if f"{sp.config.name}/{tool.name}" == qualified_name:
                    return tool
        for conn in self._http_servers.values():
            for tool in conn.tools:
                if f"{conn.config.name}/{tool.name}" == qualified_name:
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

        if server_name not in self._servers and server_name not in self._http_servers:
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

    # ── JSON-RPC transport: stdio ────────────────────────────────────────────

    async def _jsonrpc_call(
        self,
        server_name: str,
        method: str,
        params: Optional[dict] = None,
    ) -> Any:
        """Send JSON-RPC request via the appropriate transport."""
        if server_name in self._http_servers:
            return await self._jsonrpc_call_http(server_name, method, params)
        return await self._jsonrpc_call_stdio(server_name, method, params)

    async def _jsonrpc_call_stdio(
        self,
        server_name: str,
        method: str,
        params: Optional[dict] = None,
    ) -> Any:
        """Send JSON-RPC request over stdio and wait for response."""
        sp = self._servers.get(server_name)
        if sp is None or sp.process is None:
            raise RuntimeError(f"MCP server '{server_name}' is not running")

        req_id = sp.next_id()
        request: dict[str, Any] = {
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
            assert sp.process.stdin is not None
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

    # ── JSON-RPC transport: HTTP ─────────────────────────────────────────────

    async def _jsonrpc_call_http(
        self,
        server_name: str,
        method: str,
        params: Optional[dict] = None,
    ) -> Any:
        """Send JSON-RPC request over HTTP POST."""
        conn = self._http_servers.get(server_name)
        if conn is None or conn.client is None:
            raise RuntimeError(f"MCP server '{server_name}' is not connected")

        req_id = conn.next_id()
        request: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params

        headers = {"Content-Type": "application/json"}
        headers.update(conn.config.headers)

        try:
            resp = await conn.client.post(
                conn.config.url,
                json=request,
                headers=headers,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise RuntimeError(
                f"MCP HTTP request to '{server_name}' failed: {e}"
            ) from e

        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise RuntimeError(
                f"MCP server '{server_name}' returned invalid JSON: {e}"
            ) from e

        if "error" in data:
            err = data["error"]
            raise RuntimeError(
                f"MCP error: {err.get('message', err)}"
            )

        return data.get("result")

    # ── stdio reader loop ────────────────────────────────────────────────────

    async def _reader_loop(self, server_name: str) -> None:
        """Read JSON-RPC responses from stdout."""
        sp = self._servers.get(server_name)
        if sp is None or sp.process is None:
            return

        try:
            assert sp.process.stdout is not None
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

    # ── Initialize & discover: stdio ─────────────────────────────────────────

    async def _send_initialize_stdio(self, server_name: str) -> None:
        """Send MCP initialize handshake over stdio."""
        await self._jsonrpc_call_stdio(
            server_name,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "cody", "version": _version},
            },
        )
        sp = self._servers[server_name]
        if sp.process and sp.process.stdin:
            notification = json.dumps({
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }) + "\n"
            sp.process.stdin.write(notification.encode())
            await sp.process.stdin.drain()

    async def _discover_tools_stdio(self, server_name: str) -> None:
        """Discover tools from a stdio MCP server."""
        result = await self._jsonrpc_call_stdio(server_name, "tools/list", {})

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

    # ── Initialize & discover: HTTP ──────────────────────────────────────────

    async def _send_initialize_http(self, server_name: str) -> None:
        """Send MCP initialize handshake over HTTP."""
        await self._jsonrpc_call_http(
            server_name,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "cody", "version": _version},
            },
        )

    async def _discover_tools_http(self, server_name: str) -> None:
        """Discover tools from an HTTP MCP server."""
        result = await self._jsonrpc_call_http(server_name, "tools/list", {})

        conn = self._http_servers[server_name]
        conn.tools = []

        # Handle both direct and nested response formats
        tools_list = None
        if isinstance(result, dict) and "tools" in result:
            tools_list = result["tools"]
        elif isinstance(result, dict) and "result" in result:
            inner = result["result"]
            if isinstance(inner, dict) and "tools" in inner:
                tools_list = inner["tools"]

        if tools_list:
            for t in tools_list:
                conn.tools.append(MCPTool(
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
        return list(self._servers.keys()) + list(self._http_servers.keys())
