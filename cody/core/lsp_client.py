"""LSP (Language Server Protocol) Client integration.

Manages LSP server processes and provides code intelligence tools to the agent:
- Diagnostics (errors/warnings from the compiler)
- Go-to-definition
- Find references
- Hover information

Supported language servers:
- Python: pyright (via pyright-python)
- TypeScript/JavaScript: typescript-language-server
- Go: gopls
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional
logger = logging.getLogger(__name__)


class LanguageId(str, Enum):
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    GO = "go"


# Known language server commands
_LANGUAGE_SERVERS: dict[str, dict[str, Any]] = {
    "python": {
        "command": "pyright-langserver",
        "args": ["--stdio"],
        "extensions": {".py", ".pyi"},
    },
    "typescript": {
        "command": "typescript-language-server",
        "args": ["--stdio"],
        "extensions": {".ts", ".tsx", ".js", ".jsx"},
    },
    "go": {
        "command": "gopls",
        "args": ["serve"],
        "extensions": {".go"},
    },
}


@dataclass
class Diagnostic:
    """A single diagnostic (error/warning) from LSP."""
    file: str
    line: int
    character: int
    severity: str  # "error", "warning", "info", "hint"
    message: str
    source: Optional[str] = None

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.character}: [{self.severity}] {self.message}"


@dataclass
class Location:
    """A file location from LSP."""
    file: str
    line: int
    character: int

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.character}"


@dataclass
class HoverInfo:
    """Hover information for a symbol."""
    content: str
    language: Optional[str] = None


_SEVERITY_MAP = {1: "error", 2: "warning", 3: "info", 4: "hint"}


def _uri_to_path(uri: str, workdir: Path) -> str:
    """Convert file:// URI to relative path."""
    if uri.startswith("file://"):
        abs_path = uri[7:]
        try:
            return str(Path(abs_path).relative_to(workdir))
        except ValueError:
            return abs_path
    return uri


def _path_to_uri(path: str, workdir: Path) -> str:
    """Convert relative path to file:// URI."""
    abs_path = (workdir / path).resolve()
    return f"file://{abs_path}"


class LSPClient:
    """Manage LSP server lifecycle and proxy requests.

    Usage:
        lsp = LSPClient(workdir=Path("/project"))
        await lsp.start("python")
        diags = await lsp.get_diagnostics("src/main.py")
        loc = await lsp.goto_definition("src/main.py", 10, 5)
        await lsp.stop_all()
    """

    def __init__(self, workdir: Path):
        self.workdir = workdir.resolve()
        self._servers: dict[str, "_LSPServer"] = {}

    async def start(self, language: str) -> bool:
        """Start an LSP server for the given language. Returns True on success."""
        if language in self._servers:
            return True

        spec = _LANGUAGE_SERVERS.get(language)
        if spec is None:
            logger.warning("No LSP server known for language: %s", language)
            return False

        server = _LSPServer(
            language=language,
            command=spec["command"],
            args=spec["args"],
            extensions=spec["extensions"],
            workdir=self.workdir,
        )

        try:
            await server.start()
            self._servers[language] = server
            logger.info("LSP server '%s' started (pid=%s)", language, server.pid)
            return True
        except Exception as e:
            logger.error("Failed to start LSP server '%s': %s", language, e)
            return False

    async def stop(self, language: str) -> None:
        """Stop an LSP server."""
        server = self._servers.pop(language, None)
        if server:
            await server.stop()

    async def stop_all(self) -> None:
        for lang in list(self._servers):
            await self.stop(lang)

    @property
    def running_servers(self) -> list[str]:
        return list(self._servers.keys())

    def _server_for_file(self, file_path: str) -> Optional["_LSPServer"]:
        """Find the appropriate LSP server for a file extension."""
        ext = Path(file_path).suffix
        for server in self._servers.values():
            if ext in server.extensions:
                return server
        return None

    # ── High-level API ───────────────────────────────────────────────────────

    async def get_diagnostics(self, file_path: str) -> list[Diagnostic]:
        """Get diagnostics for a file (open it first to trigger analysis)."""
        server = self._server_for_file(file_path)
        if server is None:
            return []

        uri = _path_to_uri(file_path, self.workdir)
        full_path = self.workdir / file_path

        if not full_path.exists():
            return []

        content = full_path.read_text(errors="ignore")
        await server.did_open(uri, server.language, content)

        # Give the server a moment to analyze
        await asyncio.sleep(0.5)

        return server.get_cached_diagnostics(uri)

    async def goto_definition(
        self, file_path: str, line: int, character: int
    ) -> Optional[Location]:
        """Go to the definition of a symbol."""
        server = self._server_for_file(file_path)
        if server is None:
            return None

        uri = _path_to_uri(file_path, self.workdir)
        result = await server.request(
            "textDocument/definition",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line - 1, "character": character},
            },
        )

        if not result:
            return None

        # Result can be Location | Location[] | LocationLink[]
        loc = result[0] if isinstance(result, list) else result
        target_uri = loc.get("uri") or loc.get("targetUri", "")
        pos = loc.get("range", loc.get("targetRange", {})).get("start", {})

        return Location(
            file=_uri_to_path(target_uri, self.workdir),
            line=pos.get("line", 0) + 1,
            character=pos.get("character", 0),
        )

    async def find_references(
        self, file_path: str, line: int, character: int
    ) -> list[Location]:
        """Find all references to a symbol."""
        server = self._server_for_file(file_path)
        if server is None:
            return []

        uri = _path_to_uri(file_path, self.workdir)
        result = await server.request(
            "textDocument/references",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line - 1, "character": character},
                "context": {"includeDeclaration": True},
            },
        )

        if not result:
            return []

        locations: list[Location] = []
        for loc in result:
            target_uri = loc.get("uri", "")
            pos = loc.get("range", {}).get("start", {})
            locations.append(Location(
                file=_uri_to_path(target_uri, self.workdir),
                line=pos.get("line", 0) + 1,
                character=pos.get("character", 0),
            ))

        return locations

    async def hover(
        self, file_path: str, line: int, character: int
    ) -> Optional[HoverInfo]:
        """Get hover information for a position."""
        server = self._server_for_file(file_path)
        if server is None:
            return None

        uri = _path_to_uri(file_path, self.workdir)
        result = await server.request(
            "textDocument/hover",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line - 1, "character": character},
            },
        )

        if not result:
            return None

        contents = result.get("contents", "")
        if isinstance(contents, dict):
            return HoverInfo(
                content=contents.get("value", ""),
                language=contents.get("language"),
            )
        if isinstance(contents, list):
            parts = []
            for c in contents:
                if isinstance(c, dict):
                    parts.append(c.get("value", ""))
                else:
                    parts.append(str(c))
            return HoverInfo(content="\n".join(parts))
        return HoverInfo(content=str(contents))

    # ── Context manager ─────────────────────────────────────────────────────

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.stop_all()


class _LSPServer:
    """Internal: a single LSP server process."""

    def __init__(
        self,
        language: str,
        command: str,
        args: list[str],
        extensions: set[str],
        workdir: Path,
    ):
        self.language = language
        self.command = command
        self.args = args
        self.extensions = extensions
        self.workdir = workdir

        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._diagnostics: dict[str, list[Diagnostic]] = {}
        self._buf = b""

    @property
    def pid(self) -> Optional[int]:
        return self._process.pid if self._process else None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._process = await asyncio.create_subprocess_exec(
            self.command, *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._reader_loop())
        await self._initialize()

    async def stop(self) -> None:
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        if self._process and self._process.returncode is None:
            try:
                await self.request("shutdown", {})
                self._send_notification("exit", {})
                await asyncio.wait_for(self._process.wait(), timeout=3.0)
            except Exception:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()

    # ── JSON-RPC ─────────────────────────────────────────────────────────────

    async def request(self, method: str, params: dict) -> Any:
        """Send JSON-RPC request, wait for response."""
        self._request_id += 1
        req_id = self._request_id

        msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        self._send_message(msg)

        try:
            return await asyncio.wait_for(future, timeout=15.0)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            return None

    def _send_notification(self, method: str, params: dict) -> None:
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        self._send_message(msg)

    def _send_message(self, msg: dict) -> None:
        if self._process is None or self._process.stdin is None:
            return
        body = json.dumps(msg).encode()
        header = f"Content-Length: {len(body)}\r\n\r\n".encode()
        self._process.stdin.write(header + body)

    async def _reader_loop(self) -> None:
        """Read LSP messages from stdout (Content-Length framing)."""
        if self._process is None or self._process.stdout is None:
            return

        try:
            while True:
                # Read headers
                header_data = b""
                while b"\r\n\r\n" not in header_data:
                    chunk = await self._process.stdout.read(1)
                    if not chunk:
                        return
                    header_data += chunk

                # Parse Content-Length
                content_length = 0
                for header_line in header_data.decode("ascii", errors="ignore").split("\r\n"):
                    if header_line.lower().startswith("content-length:"):
                        content_length = int(header_line.split(":")[1].strip())
                        break

                if content_length == 0:
                    continue

                body = await self._process.stdout.readexactly(content_length)
                try:
                    msg = json.loads(body)
                except json.JSONDecodeError:
                    continue

                self._handle_message(msg)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("LSP reader error for '%s': %s", self.language, e)

    def _handle_message(self, msg: dict) -> None:
        """Handle incoming LSP message."""
        # Response to a request
        if "id" in msg and "method" not in msg:
            req_id = msg["id"]
            future = self._pending.pop(req_id, None)
            if future and not future.done():
                if "error" in msg:
                    future.set_result(None)
                else:
                    future.set_result(msg.get("result"))
            return

        # Notification
        method = msg.get("method", "")
        if method == "textDocument/publishDiagnostics":
            self._handle_diagnostics(msg.get("params", {}))

    def _handle_diagnostics(self, params: dict) -> None:
        """Cache diagnostics from server."""
        uri = params.get("uri", "")
        diags: list[Diagnostic] = []
        for d in params.get("diagnostics", []):
            rng = d.get("range", {}).get("start", {})
            diags.append(Diagnostic(
                file=_uri_to_path(uri, self.workdir),
                line=rng.get("line", 0) + 1,
                character=rng.get("character", 0),
                severity=_SEVERITY_MAP.get(d.get("severity", 4), "hint"),
                message=d.get("message", ""),
                source=d.get("source"),
            ))
        self._diagnostics[uri] = diags

    def get_cached_diagnostics(self, uri: str) -> list[Diagnostic]:
        return self._diagnostics.get(uri, [])

    # ── LSP protocol messages ────────────────────────────────────────────────

    async def _initialize(self) -> None:
        """Send LSP initialize + initialized."""
        await self.request(
            "initialize",
            {
                "processId": None,
                "rootUri": f"file://{self.workdir}",
                "capabilities": {
                    "textDocument": {
                        "publishDiagnostics": {"relatedInformation": True},
                        "definition": {"dynamicRegistration": False},
                        "references": {"dynamicRegistration": False},
                        "hover": {"dynamicRegistration": False, "contentFormat": ["markdown"]},
                    }
                },
            },
        )
        self._send_notification("initialized", {})

    async def did_open(self, uri: str, language_id: str, text: str) -> None:
        """Notify server that a file was opened."""
        self._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": language_id,
                "version": 1,
                "text": text,
            },
        })
