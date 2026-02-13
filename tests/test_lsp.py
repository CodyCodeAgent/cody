"""Tests for LSP Client module"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from cody.core.lsp_client import (
    Diagnostic,
    HoverInfo,
    LanguageId,
    Location,
    LSPClient,
    _LANGUAGE_SERVERS,
    _SEVERITY_MAP,
    _uri_to_path,
    _path_to_uri,
)


# ── LanguageId enum ──────────────────────────────────────────────────────────


def test_language_id_values():
    assert LanguageId.PYTHON == "python"
    assert LanguageId.TYPESCRIPT == "typescript"
    assert LanguageId.JAVASCRIPT == "javascript"
    assert LanguageId.GO == "go"


# ── Language server specs ────────────────────────────────────────────────────


def test_language_servers_python():
    spec = _LANGUAGE_SERVERS["python"]
    assert spec["command"] == "pyright-langserver"
    assert ".py" in spec["extensions"]


def test_language_servers_typescript():
    spec = _LANGUAGE_SERVERS["typescript"]
    assert ".ts" in spec["extensions"]
    assert ".tsx" in spec["extensions"]


def test_language_servers_go():
    spec = _LANGUAGE_SERVERS["go"]
    assert spec["command"] == "gopls"
    assert ".go" in spec["extensions"]


# ── Dataclass tests ──────────────────────────────────────────────────────────


def test_diagnostic_str():
    d = Diagnostic(
        file="src/main.py",
        line=10,
        character=5,
        severity="error",
        message="Undefined variable 'x'",
        source="pyright",
    )
    s = str(d)
    assert "src/main.py:10:5" in s
    assert "[error]" in s
    assert "Undefined variable" in s


def test_location_str():
    loc = Location(file="src/main.py", line=15, character=3)
    assert str(loc) == "src/main.py:15:3"


def test_hover_info():
    h = HoverInfo(content="def foo() -> int", language="python")
    assert h.content == "def foo() -> int"
    assert h.language == "python"


def test_hover_info_no_language():
    h = HoverInfo(content="some text")
    assert h.language is None


# ── URI helpers ──────────────────────────────────────────────────────────────


def test_uri_to_path(tmp_path):
    uri = f"file://{tmp_path}/src/main.py"
    result = _uri_to_path(uri, tmp_path)
    assert result == "src/main.py"


def test_uri_to_path_outside_workdir(tmp_path):
    uri = "file:///some/other/path.py"
    result = _uri_to_path(uri, tmp_path)
    assert result == "/some/other/path.py"


def test_uri_to_path_not_file_uri():
    result = _uri_to_path("https://example.com", Path("/tmp"))
    assert result == "https://example.com"


def test_path_to_uri(tmp_path):
    uri = _path_to_uri("src/main.py", tmp_path)
    assert uri.startswith("file://")
    assert "src/main.py" in uri


# ── Severity map ─────────────────────────────────────────────────────────────


def test_severity_map():
    assert _SEVERITY_MAP[1] == "error"
    assert _SEVERITY_MAP[2] == "warning"
    assert _SEVERITY_MAP[3] == "info"
    assert _SEVERITY_MAP[4] == "hint"


# ── LSPClient init ───────────────────────────────────────────────────────────


def test_lsp_client_init(tmp_path):
    client = LSPClient(workdir=tmp_path)
    assert client.workdir == tmp_path.resolve()
    assert client.running_servers == []


# ── LSPClient start (mocked) ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_unknown_language(tmp_path):
    client = LSPClient(workdir=tmp_path)
    result = await client.start("brainfuck")
    assert result is False
    assert client.running_servers == []


@pytest.mark.asyncio
async def test_start_already_running(tmp_path):
    client = LSPClient(workdir=tmp_path)
    # Manually add a "server" to simulate already running
    client._servers["python"] = MagicMock()
    result = await client.start("python")
    assert result is True  # no-op, returns True


@pytest.mark.asyncio
async def test_start_subprocess_fails(tmp_path):
    """If subprocess launch fails, start returns False"""
    client = LSPClient(workdir=tmp_path)

    with patch("cody.core.lsp_client._LSPServer.start", new_callable=AsyncMock) as mock_start:
        mock_start.side_effect = FileNotFoundError("pyright-langserver not found")
        result = await client.start("python")

    assert result is False
    assert "python" not in client._servers


# ── LSPClient server_for_file ────────────────────────────────────────────────


def test_server_for_file_no_match(tmp_path):
    client = LSPClient(workdir=tmp_path)
    assert client._server_for_file("test.rs") is None


def test_server_for_file_match(tmp_path):
    client = LSPClient(workdir=tmp_path)
    mock_server = MagicMock()
    mock_server.extensions = {".py", ".pyi"}
    client._servers["python"] = mock_server

    assert client._server_for_file("main.py") == mock_server
    assert client._server_for_file("types.pyi") == mock_server
    assert client._server_for_file("main.js") is None


# ── LSPClient high-level API (mocked server) ────────────────────────────────


@pytest.mark.asyncio
async def test_get_diagnostics_no_server(tmp_path):
    client = LSPClient(workdir=tmp_path)
    diags = await client.get_diagnostics("main.rs")
    assert diags == []


@pytest.mark.asyncio
async def test_get_diagnostics_file_not_found(tmp_path):
    client = LSPClient(workdir=tmp_path)
    mock_server = MagicMock()
    mock_server.extensions = {".py"}
    mock_server.language = "python"
    client._servers["python"] = mock_server

    diags = await client.get_diagnostics("nonexistent.py")
    assert diags == []


@pytest.mark.asyncio
async def test_get_diagnostics_with_file(tmp_path):
    # Create a test file
    test_file = tmp_path / "test.py"
    test_file.write_text("import os\n")

    client = LSPClient(workdir=tmp_path)
    mock_server = MagicMock()
    mock_server.extensions = {".py"}
    mock_server.language = "python"
    mock_server.did_open = AsyncMock()
    mock_server.get_cached_diagnostics = MagicMock(return_value=[
        Diagnostic(file="test.py", line=1, character=0, severity="warning", message="unused import"),
    ])
    client._servers["python"] = mock_server

    diags = await client.get_diagnostics("test.py")
    assert len(diags) == 1
    assert diags[0].severity == "warning"
    mock_server.did_open.assert_called_once()


@pytest.mark.asyncio
async def test_goto_definition_no_server(tmp_path):
    client = LSPClient(workdir=tmp_path)
    result = await client.goto_definition("main.rs", 1, 0)
    assert result is None


@pytest.mark.asyncio
async def test_goto_definition_with_result(tmp_path):
    client = LSPClient(workdir=tmp_path)
    mock_server = MagicMock()
    mock_server.extensions = {".py"}
    mock_server.request = AsyncMock(return_value=[
        {
            "uri": f"file://{tmp_path}/utils.py",
            "range": {"start": {"line": 4, "character": 0}, "end": {"line": 4, "character": 10}},
        }
    ])
    client._servers["python"] = mock_server

    loc = await client.goto_definition("main.py", 10, 5)
    assert loc is not None
    assert loc.line == 5  # 4 + 1 (0-indexed to 1-indexed)
    assert "utils.py" in loc.file


@pytest.mark.asyncio
async def test_goto_definition_no_result(tmp_path):
    client = LSPClient(workdir=tmp_path)
    mock_server = MagicMock()
    mock_server.extensions = {".py"}
    mock_server.request = AsyncMock(return_value=None)
    client._servers["python"] = mock_server

    loc = await client.goto_definition("main.py", 1, 0)
    assert loc is None


@pytest.mark.asyncio
async def test_find_references_with_results(tmp_path):
    client = LSPClient(workdir=tmp_path)
    mock_server = MagicMock()
    mock_server.extensions = {".py"}
    mock_server.request = AsyncMock(return_value=[
        {
            "uri": f"file://{tmp_path}/a.py",
            "range": {"start": {"line": 0, "character": 0}},
        },
        {
            "uri": f"file://{tmp_path}/b.py",
            "range": {"start": {"line": 9, "character": 4}},
        },
    ])
    client._servers["python"] = mock_server

    locs = await client.find_references("main.py", 5, 3)
    assert len(locs) == 2
    assert locs[0].line == 1
    assert locs[1].line == 10


@pytest.mark.asyncio
async def test_find_references_empty(tmp_path):
    client = LSPClient(workdir=tmp_path)
    mock_server = MagicMock()
    mock_server.extensions = {".py"}
    mock_server.request = AsyncMock(return_value=None)
    client._servers["python"] = mock_server

    locs = await client.find_references("main.py", 5, 3)
    assert locs == []


@pytest.mark.asyncio
async def test_hover_with_dict_content(tmp_path):
    client = LSPClient(workdir=tmp_path)
    mock_server = MagicMock()
    mock_server.extensions = {".py"}
    mock_server.request = AsyncMock(return_value={
        "contents": {"language": "python", "value": "def foo() -> int"},
    })
    client._servers["python"] = mock_server

    info = await client.hover("main.py", 5, 3)
    assert info is not None
    assert info.content == "def foo() -> int"
    assert info.language == "python"


@pytest.mark.asyncio
async def test_hover_with_string_content(tmp_path):
    client = LSPClient(workdir=tmp_path)
    mock_server = MagicMock()
    mock_server.extensions = {".py"}
    mock_server.request = AsyncMock(return_value={
        "contents": "Simple hover text",
    })
    client._servers["python"] = mock_server

    info = await client.hover("main.py", 5, 3)
    assert info is not None
    assert info.content == "Simple hover text"


@pytest.mark.asyncio
async def test_hover_with_list_content(tmp_path):
    client = LSPClient(workdir=tmp_path)
    mock_server = MagicMock()
    mock_server.extensions = {".py"}
    mock_server.request = AsyncMock(return_value={
        "contents": [
            {"language": "python", "value": "def foo()"},
            "Documentation for foo",
        ],
    })
    client._servers["python"] = mock_server

    info = await client.hover("main.py", 5, 3)
    assert info is not None
    assert "def foo()" in info.content
    assert "Documentation for foo" in info.content


@pytest.mark.asyncio
async def test_hover_no_result(tmp_path):
    client = LSPClient(workdir=tmp_path)
    mock_server = MagicMock()
    mock_server.extensions = {".py"}
    mock_server.request = AsyncMock(return_value=None)
    client._servers["python"] = mock_server

    info = await client.hover("main.py", 5, 3)
    assert info is None


# ── LSPClient stop ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stop_all(tmp_path):
    client = LSPClient(workdir=tmp_path)
    mock_server = MagicMock()
    mock_server.stop = AsyncMock()
    client._servers["python"] = mock_server

    await client.stop_all()
    assert client._servers == {}
    mock_server.stop.assert_called_once()


@pytest.mark.asyncio
async def test_stop_specific(tmp_path):
    client = LSPClient(workdir=tmp_path)
    mock_py = MagicMock()
    mock_py.stop = AsyncMock()
    mock_ts = MagicMock()
    mock_ts.stop = AsyncMock()
    client._servers["python"] = mock_py
    client._servers["typescript"] = mock_ts

    await client.stop("python")
    assert "python" not in client._servers
    assert "typescript" in client._servers
    mock_py.stop.assert_called_once()


# ── Context manager ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_context_manager(tmp_path):
    async with LSPClient(workdir=tmp_path) as client:
        assert client.running_servers == []
    # After exit, stop_all is called (no servers to stop here, just verify no error)
