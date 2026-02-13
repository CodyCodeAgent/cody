"""Python SDK for Cody RPC Server.

Usage:
    from cody import CodyClient

    client = CodyClient("http://localhost:8000")

    # One-shot
    result = client.run("create hello.py")
    print(result.output)

    # Multi-turn session
    session = client.create_session()
    r1 = client.run("create a Flask app", session_id=session.id)
    r2 = client.run("add a /health endpoint", session_id=session.id)

    # Async
    async with AsyncCodyClient("http://localhost:8000") as client:
        result = await client.run("create hello.py")
        async for chunk in client.stream("explain this code"):
            print(chunk.content, end="")

    # Auto-reconnect (enabled by default)
    client = CodyClient("http://localhost:8000", max_retries=3)
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Iterator, Optional, TypeVar

import httpx


T = TypeVar("T")


# ── Response types ───────────────────────────────────────────────────────────


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class RunResult:
    output: str
    session_id: Optional[str] = None
    usage: Usage = field(default_factory=Usage)


@dataclass
class StreamChunk:
    type: str  # "text", "done", "error"
    content: str = ""
    session_id: Optional[str] = None


@dataclass
class SessionInfo:
    id: str
    title: str
    model: str
    workdir: str
    message_count: int
    created_at: str
    updated_at: str


@dataclass
class SessionDetail(SessionInfo):
    messages: list[dict] = field(default_factory=list)


@dataclass
class ToolResult:
    result: str


# ── Errors ───────────────────────────────────────────────────────────────────


class CodyError(Exception):
    """Base error for Cody SDK."""
    def __init__(self, message: str, status_code: int = 0, code: Optional[str] = None):
        self.message = message
        self.status_code = status_code
        self.code = code
        super().__init__(message)


class CodyConnectionError(CodyError):
    """Server is unreachable."""
    pass


class CodyNotFoundError(CodyError):
    """Resource not found (404)."""
    pass


class CodyTimeoutError(CodyError):
    """Request timed out."""
    pass


# ── Retry helpers ────────────────────────────────────────────────────────────

_RETRYABLE_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout)


def _should_retry(exc: Exception) -> bool:
    return isinstance(exc, _RETRYABLE_ERRORS)


def _backoff_delay(attempt: int, base: float = 0.5, max_delay: float = 8.0) -> float:
    """Exponential backoff: 0.5s, 1s, 2s, 4s, 8s (capped)."""
    return min(base * (2 ** attempt), max_delay)


# ── Shared error extraction ─────────────────────────────────────────────────


def _extract_error(resp: httpx.Response) -> tuple[str, Optional[str]]:
    """Extract message and error code from response."""
    try:
        body = resp.json()
    except Exception:
        return resp.text, None
    # Structured format: {"error": {"code": "...", "message": "..."}}
    if "error" in body and isinstance(body["error"], dict):
        return body["error"].get("message", resp.text), body["error"].get("code")
    # Legacy format: {"detail": "..."}
    return body.get("detail", resp.text), None


def _handle_error(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    message, code = _extract_error(resp)
    if resp.status_code == 404:
        raise CodyNotFoundError(message, status_code=404, code=code)
    raise CodyError(message, status_code=resp.status_code, code=code)


# ── Async client ─────────────────────────────────────────────────────────────


class AsyncCodyClient:
    """Async Python client for Cody RPC Server.

    Args:
        base_url: Server URL.
        timeout: Request timeout in seconds.
        max_retries: Max retry attempts on transient failures (0 = no retry).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 120.0,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def close(self):
        await self._client.aclose()

    # ── Internal retry helpers ────────────────────────────────────────────

    async def _retry(self, fn: Callable, *args, **kwargs):
        """Call *fn* with retry + exponential backoff on transient errors."""
        last_exc: Optional[Exception] = None
        for attempt in range(1 + self.max_retries):
            try:
                return await fn(*args, **kwargs)
            except _RETRYABLE_ERRORS as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(_backoff_delay(attempt))
        raise CodyConnectionError(
            f"Cannot connect to {self.base_url} after {self.max_retries + 1} attempts: {last_exc}"
        )

    # ── Health ───────────────────────────────────────────────────────────────

    async def health(self) -> dict:
        """Check server health."""
        resp = await self._retry(self._client.get, "/health")
        _handle_error(resp)
        return resp.json()

    # ── Run ──────────────────────────────────────────────────────────────────

    async def run(
        self,
        prompt: str,
        *,
        workdir: Optional[str] = None,
        model: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> RunResult:
        """Run agent with prompt. Returns result."""
        body: dict = {"prompt": prompt}
        if workdir:
            body["workdir"] = workdir
        if model:
            body["model"] = model
        if session_id is not None:
            body["session_id"] = session_id

        resp = await self._retry(self._client.post, "/run", json=body)
        _handle_error(resp)

        data = resp.json()
        usage_data = data.get("usage") or {}
        return RunResult(
            output=data["output"],
            session_id=data.get("session_id"),
            usage=Usage(
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            ),
        )

    async def stream(
        self,
        prompt: str,
        *,
        workdir: Optional[str] = None,
        model: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream agent response. Yields StreamChunk objects."""
        body: dict = {"prompt": prompt}
        if workdir:
            body["workdir"] = workdir
        if model:
            body["model"] = model
        if session_id is not None:
            body["session_id"] = session_id

        try:
            async with self._client.stream("POST", "/run/stream", json=body) as resp:
                _handle_error(resp)
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = json.loads(line[6:])
                    yield StreamChunk(
                        type=data.get("type", "text"),
                        content=data.get("content", ""),
                        session_id=data.get("session_id"),
                    )
        except _RETRYABLE_ERRORS as e:
            raise CodyConnectionError(f"Cannot connect to {self.base_url}: {e}")

    # ── Tool ─────────────────────────────────────────────────────────────────

    async def tool(
        self,
        tool_name: str,
        params: Optional[dict] = None,
        *,
        workdir: Optional[str] = None,
    ) -> ToolResult:
        """Call a tool directly."""
        body: dict = {"tool": tool_name, "params": params or {}}
        if workdir:
            body["workdir"] = workdir

        resp = await self._retry(self._client.post, "/tool", json=body)
        _handle_error(resp)

        return ToolResult(result=resp.json()["result"])

    # ── Sessions ─────────────────────────────────────────────────────────────

    async def create_session(
        self,
        title: str = "New session",
        model: str = "",
        workdir: str = "",
    ) -> SessionInfo:
        """Create a new session."""
        resp = await self._retry(
            self._client.post, "/sessions",
            params={"title": title, "model": model, "workdir": workdir},
        )
        _handle_error(resp)

        data = resp.json()
        return SessionInfo(
            id=data["id"],
            title=data["title"],
            model=data["model"],
            workdir=data["workdir"],
            message_count=data["message_count"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    async def list_sessions(self, limit: int = 20) -> list[SessionInfo]:
        """List recent sessions."""
        resp = await self._retry(self._client.get, "/sessions", params={"limit": limit})
        _handle_error(resp)

        return [
            SessionInfo(
                id=s["id"],
                title=s["title"],
                model=s["model"],
                workdir=s["workdir"],
                message_count=s["message_count"],
                created_at=s["created_at"],
                updated_at=s["updated_at"],
            )
            for s in resp.json()["sessions"]
        ]

    async def get_session(self, session_id: str) -> SessionDetail:
        """Get session with messages."""
        resp = await self._retry(self._client.get, f"/sessions/{session_id}")
        _handle_error(resp)

        data = resp.json()
        return SessionDetail(
            id=data["id"],
            title=data["title"],
            model=data["model"],
            workdir=data["workdir"],
            message_count=data["message_count"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            messages=data["messages"],
        )

    async def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        resp = await self._retry(self._client.delete, f"/sessions/{session_id}")
        _handle_error(resp)

    # ── Skills ───────────────────────────────────────────────────────────────

    async def list_skills(self) -> list[dict]:
        """List available skills."""
        resp = await self._retry(self._client.get, "/skills")
        _handle_error(resp)
        return resp.json()["skills"]


# ── Sync client ──────────────────────────────────────────────────────────────


class CodyClient:
    """Synchronous Python client for Cody RPC Server.

    Args:
        base_url: Server URL.
        timeout: Request timeout in seconds.
        max_retries: Max retry attempts on transient failures (0 = no retry).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 120.0,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
        )

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ── Internal retry helpers ────────────────────────────────────────────

    def _retry(self, fn: Callable, *args, **kwargs):
        """Call *fn* with retry + exponential backoff on transient errors."""
        last_exc: Optional[Exception] = None
        for attempt in range(1 + self.max_retries):
            try:
                return fn(*args, **kwargs)
            except _RETRYABLE_ERRORS as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(_backoff_delay(attempt))
        raise CodyConnectionError(
            f"Cannot connect to {self.base_url} after {self.max_retries + 1} attempts: {last_exc}"
        )

    def health(self) -> dict:
        """Check server health."""
        resp = self._retry(self._client.get, "/health")
        _handle_error(resp)
        return resp.json()

    def run(
        self,
        prompt: str,
        *,
        workdir: Optional[str] = None,
        model: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> RunResult:
        """Run agent with prompt."""
        body: dict = {"prompt": prompt}
        if workdir:
            body["workdir"] = workdir
        if model:
            body["model"] = model
        if session_id is not None:
            body["session_id"] = session_id

        resp = self._retry(self._client.post, "/run", json=body)
        _handle_error(resp)

        data = resp.json()
        usage_data = data.get("usage") or {}
        return RunResult(
            output=data["output"],
            session_id=data.get("session_id"),
            usage=Usage(
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            ),
        )

    def stream(
        self,
        prompt: str,
        *,
        workdir: Optional[str] = None,
        model: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Iterator[StreamChunk]:
        """Stream agent response. Yields StreamChunk objects."""
        body: dict = {"prompt": prompt}
        if workdir:
            body["workdir"] = workdir
        if model:
            body["model"] = model
        if session_id is not None:
            body["session_id"] = session_id

        try:
            with self._client.stream("POST", "/run/stream", json=body) as resp:
                _handle_error(resp)
                for line in resp.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = json.loads(line[6:])
                    yield StreamChunk(
                        type=data.get("type", "text"),
                        content=data.get("content", ""),
                        session_id=data.get("session_id"),
                    )
        except _RETRYABLE_ERRORS as e:
            raise CodyConnectionError(f"Cannot connect to {self.base_url}: {e}")

    def tool(
        self,
        tool_name: str,
        params: Optional[dict] = None,
        *,
        workdir: Optional[str] = None,
    ) -> ToolResult:
        """Call a tool directly."""
        body: dict = {"tool": tool_name, "params": params or {}}
        if workdir:
            body["workdir"] = workdir

        resp = self._retry(self._client.post, "/tool", json=body)
        _handle_error(resp)
        return ToolResult(result=resp.json()["result"])

    def create_session(
        self,
        title: str = "New session",
        model: str = "",
        workdir: str = "",
    ) -> SessionInfo:
        """Create a new session."""
        resp = self._retry(
            self._client.post, "/sessions",
            params={"title": title, "model": model, "workdir": workdir},
        )
        _handle_error(resp)

        data = resp.json()
        return SessionInfo(
            id=data["id"],
            title=data["title"],
            model=data["model"],
            workdir=data["workdir"],
            message_count=data["message_count"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    def list_sessions(self, limit: int = 20) -> list[SessionInfo]:
        """List recent sessions."""
        resp = self._retry(self._client.get, "/sessions", params={"limit": limit})
        _handle_error(resp)

        return [
            SessionInfo(
                id=s["id"],
                title=s["title"],
                model=s["model"],
                workdir=s["workdir"],
                message_count=s["message_count"],
                created_at=s["created_at"],
                updated_at=s["updated_at"],
            )
            for s in resp.json()["sessions"]
        ]

    def get_session(self, session_id: str) -> SessionDetail:
        """Get session with messages."""
        resp = self._retry(self._client.get, f"/sessions/{session_id}")
        _handle_error(resp)

        data = resp.json()
        return SessionDetail(
            id=data["id"],
            title=data["title"],
            model=data["model"],
            workdir=data["workdir"],
            message_count=data["message_count"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            messages=data["messages"],
        )

    def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        resp = self._retry(self._client.delete, f"/sessions/{session_id}")
        _handle_error(resp)

    # ── Skills ───────────────────────────────────────────────────────────────

    def list_skills(self) -> list[dict]:
        """List available skills."""
        resp = self._retry(self._client.get, "/skills")
        _handle_error(resp)
        return resp.json()["skills"]
