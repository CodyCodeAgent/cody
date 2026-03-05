"""Tests for MCP Client integration"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from cody.core.config import MCPConfig, MCPServerConfig
from cody.core.mcp_client import MCPClient, MCPTool, _ServerProcess


# ── MCPTool dataclass ───────────────────────────────────────────────────────


def test_mcp_tool_creation():
    tool = MCPTool(
        name="search",
        description="Search the web",
        input_schema={"type": "object"},
        server_name="web",
    )
    assert tool.name == "search"
    assert tool.server_name == "web"


# ── MCPClient init ──────────────────────────────────────────────────────────


def test_mcp_client_init_empty():
    config = MCPConfig(servers=[])
    client = MCPClient(config)
    assert client.list_tools() == []
    assert client.running_servers == []


def test_mcp_client_init_with_config():
    config = MCPConfig(servers=[
        MCPServerConfig(name="test", command="echo", args=["hello"]),
    ])
    client = MCPClient(config)
    assert len(client.config.servers) == 1


# ── Tool listing ────────────────────────────────────────────────────────────


def test_list_tools_empty():
    config = MCPConfig(servers=[])
    client = MCPClient(config)
    assert client.list_tools() == []


def test_list_tools_from_servers():
    config = MCPConfig(servers=[])
    client = MCPClient(config)

    # Simulate registered tools
    sp = _ServerProcess(
        config=MCPServerConfig(name="github", command="node", args=[]),
        tools=[
            MCPTool("create_issue", "Create issue", {}, "github"),
            MCPTool("list_prs", "List PRs", {}, "github"),
        ],
    )
    client._servers["github"] = sp

    tools = client.list_tools()
    assert len(tools) == 2
    assert tools[0].name == "create_issue"
    assert tools[1].server_name == "github"


def test_get_tool_qualified():
    config = MCPConfig(servers=[])
    client = MCPClient(config)

    sp = _ServerProcess(
        config=MCPServerConfig(name="db", command="node", args=[]),
        tools=[MCPTool("query", "Run SQL", {}, "db")],
    )
    client._servers["db"] = sp

    tool = client.get_tool("db/query")
    assert tool is not None
    assert tool.name == "query"

    assert client.get_tool("db/nonexistent") is None
    assert client.get_tool("other/query") is None


# ── call_tool validation ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_call_tool_invalid_name():
    config = MCPConfig(servers=[])
    client = MCPClient(config)

    with pytest.raises(ValueError, match="Expected 'server/tool'"):
        await client.call_tool("invalid_name")


@pytest.mark.asyncio
async def test_call_tool_server_not_running():
    config = MCPConfig(servers=[])
    client = MCPClient(config)

    with pytest.raises(ValueError, match="not running"):
        await client.call_tool("ghost/tool", {})


# ── Stop server (no-op on unknown) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_stop_unknown_server():
    config = MCPConfig(servers=[])
    client = MCPClient(config)
    await client.stop_server("nonexistent")  # should not raise


@pytest.mark.asyncio
async def test_stop_all_empty():
    config = MCPConfig(servers=[])
    client = MCPClient(config)
    await client.stop_all()  # should not raise


# ── Restart unknown ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_restart_unknown_server():
    config = MCPConfig(servers=[])
    client = MCPClient(config)
    with pytest.raises(ValueError, match="Unknown MCP server"):
        await client.restart_server("nonexistent")


# ── Context manager ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_context_manager():
    config = MCPConfig(servers=[])
    async with MCPClient(config) as client:
        assert client.running_servers == []


# ── _ServerProcess ──────────────────────────────────────────────────────────


def test_server_process_next_id():
    sp = _ServerProcess(
        config=MCPServerConfig(name="test", command="echo", args=[]),
    )
    assert sp.next_id() == 1
    assert sp.next_id() == 2
    assert sp.next_id() == 3


# ── Integration: start + discover ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_server_with_mock_process():
    """Test full start flow with mock subprocess"""
    config = MCPConfig(servers=[
        MCPServerConfig(name="mock", command="echo", args=[]),
    ])
    client = MCPClient(config)

    # Build a mock process
    mock_process = MagicMock()
    mock_process.pid = 12345
    mock_process.returncode = None
    mock_process.stdin = MagicMock()
    mock_process.stdin.write = MagicMock()
    mock_process.stdin.drain = AsyncMock()
    mock_process.stdout = MagicMock()
    mock_process.stderr = MagicMock()

    # Build a response queue — responses are enqueued by mock stdin.write
    # so the reader loop only sees them after the request is sent.
    responses = asyncio.Queue()

    # Map request id → response
    _response_map = {
        1: json.dumps({
            "jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}
        }).encode() + b"\n",
        2: json.dumps({
            "jsonrpc": "2.0", "id": 2, "result": {
                "tools": [
                    {"name": "hello", "description": "Say hello", "inputSchema": {}},
                ]
            }
        }).encode() + b"\n",
    }

    _original_write = mock_process.stdin.write

    def _mock_write(data):
        """When a request is written, enqueue the corresponding response."""
        _original_write(data)
        try:
            msg = json.loads(data)
            req_id = msg.get("id")
            if req_id in _response_map:
                responses.put_nowait(_response_map[req_id])
        except (json.JSONDecodeError, ValueError):
            pass

    mock_process.stdin.write = _mock_write

    async def mock_readline():
        try:
            return await asyncio.wait_for(responses.get(), timeout=2.0)
        except asyncio.TimeoutError:
            return b""

    mock_process.stdout.readline = mock_readline

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        await client.start_server(config.servers[0])

    assert "mock" in client.running_servers
    tools = client.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "hello"
    assert tools[0].server_name == "mock"

    # Clean up
    mock_process.terminate = MagicMock()
    mock_process.wait = AsyncMock()
    mock_process.kill = MagicMock()
    await client.stop_all()
