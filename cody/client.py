"""Python SDK for Cody — in-process wrapper around core.

No HTTP server required. The SDK imports core directly.

Usage:
    from cody import CodyClient, AsyncCodyClient

    # Async (recommended)
    async with AsyncCodyClient() as client:
        result = await client.run("create hello.py")
        print(result.output)

        # Streaming
        async for chunk in client.stream("explain this code"):
            print(chunk.content, end="")

        # Multi-turn session
        session = await client.create_session()
        r1 = await client.run("create a Flask app", session_id=session.id)
        r2 = await client.run("add a /health endpoint", session_id=session.id)

    # Sync
    with CodyClient() as client:
        result = client.run("create hello.py")
        print(result.output)
"""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Optional

from .core.config import Config
from .core.runner import (
    AgentRunner,
    CodyResult,
    CompactEvent,
    DoneEvent,
    StreamEvent,
    TextDeltaEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from .core.session import SessionStore
from .core.skill_manager import SkillManager


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
    type: str  # "text_delta", "thinking", "tool_call", "tool_result", "done", "compact"
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


class CodyNotFoundError(CodyError):
    """Resource not found."""


# ── Stream event conversion ──────────────────────────────────────────────────


def _event_to_chunk(event: StreamEvent, session_id: Optional[str] = None) -> StreamChunk:
    """Convert a core StreamEvent to an SDK StreamChunk."""
    if isinstance(event, TextDeltaEvent):
        return StreamChunk(type="text_delta", content=event.content, session_id=session_id)
    elif isinstance(event, ThinkingEvent):
        return StreamChunk(type="thinking", content=event.content, session_id=session_id)
    elif isinstance(event, ToolCallEvent):
        return StreamChunk(type="tool_call", content=event.tool_name, session_id=session_id)
    elif isinstance(event, ToolResultEvent):
        return StreamChunk(type="tool_result", content=event.result, session_id=session_id)
    elif isinstance(event, CompactEvent):
        return StreamChunk(type="compact", session_id=session_id)
    elif isinstance(event, DoneEvent):
        return StreamChunk(type="done", content=event.result.output, session_id=session_id)
    return StreamChunk(type="unknown", session_id=session_id)


def _usage_from_result(result: CodyResult) -> Usage:
    """Extract Usage from a CodyResult."""
    raw = result.usage()
    if raw is None:
        return Usage()
    input_t = getattr(raw, "input_tokens", 0) or 0
    output_t = getattr(raw, "output_tokens", 0) or 0
    total_t = getattr(raw, "total_tokens", 0)
    if not total_t:
        total_t = input_t + output_t
    return Usage(input_tokens=input_t, output_tokens=output_t, total_tokens=total_t)


# ── Async client ─────────────────────────────────────────────────────────────


class AsyncCodyClient:
    """Async Python SDK for Cody — in-process wrapper around core.

    Args:
        workdir: Working directory. Defaults to cwd.
        model: Override model (e.g. "anthropic:claude-sonnet-4-0").
        db_path: Path for session database. Defaults to ~/.cody/sessions.db.
    """

    def __init__(
        self,
        workdir: Optional[str] = None,
        *,
        model: Optional[str] = None,
        db_path: Optional[str] = None,
    ):
        self.workdir = Path(workdir) if workdir else Path.cwd()
        self._model_override = model
        self._db_path = Path(db_path) if db_path else None
        self._runner: Optional[AgentRunner] = None
        self._session_store: Optional[SessionStore] = None
        self._config: Optional[Config] = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    def _get_config(self) -> Config:
        if self._config is None:
            self._config = Config.load(workdir=self.workdir)
            if self._model_override:
                self._config.model = self._model_override
        return self._config

    def _get_runner(self) -> AgentRunner:
        if self._runner is None:
            self._runner = AgentRunner(config=self._get_config(), workdir=self.workdir)
        return self._runner

    def _get_session_store(self) -> SessionStore:
        if self._session_store is None:
            self._session_store = SessionStore(db_path=self._db_path)
        return self._session_store

    async def close(self):
        """Clean up resources."""
        if self._runner:
            await self._runner.stop_mcp()
            await self._runner.stop_lsp()
            self._runner = None

    # ── Health ───────────────────────────────────────────────────────────────

    async def health(self) -> dict:
        """Return SDK health info."""
        from . import __version__
        return {"status": "ok", "version": __version__}

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
        runner = self._get_runner()

        if session_id:
            store = self._get_session_store()
            result, sid = await runner.run_with_session(prompt, store, session_id)
        else:
            result = await runner.run(prompt)
            sid = None

        return RunResult(
            output=result.output,
            session_id=sid,
            usage=_usage_from_result(result),
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
        runner = self._get_runner()

        if session_id:
            store = self._get_session_store()
            async for event, sid in runner.run_stream_with_session(prompt, store, session_id):
                yield _event_to_chunk(event, sid)
        else:
            async for event in runner.run_stream(prompt):
                yield _event_to_chunk(event)

    # ── Tool ─────────────────────────────────────────────────────────────────

    async def tool(
        self,
        tool_name: str,
        params: Optional[dict] = None,
        *,
        workdir: Optional[str] = None,
    ) -> ToolResult:
        """Call a tool directly."""
        from .core import tools
        from .core.deps import CodyDeps

        tool_func = getattr(tools, tool_name, None)
        if not tool_func:
            raise CodyNotFoundError(
                f"Tool not found: {tool_name}",
                code="TOOL_NOT_FOUND",
            )

        effective_workdir = Path(workdir) if workdir else self.workdir
        config = Config.load(workdir=effective_workdir)

        # Create minimal deps for tool execution
        sm = SkillManager(config=config, workdir=effective_workdir)
        deps = CodyDeps(
            config=config,
            workdir=effective_workdir,
            skill_manager=sm,
            allowed_roots=[effective_workdir],
        )

        class ToolContext:
            def __init__(self, d):
                self.deps = d

        ctx = ToolContext(deps)
        result = await tool_func(ctx, **(params or {}))
        return ToolResult(result=result)

    # ── Sessions ─────────────────────────────────────────────────────────────

    async def create_session(
        self,
        title: str = "New session",
        model: str = "",
        workdir: str = "",
    ) -> SessionInfo:
        """Create a new session."""
        store = self._get_session_store()
        session = store.create_session(
            title=title,
            model=model,
            workdir=workdir or str(self.workdir),
        )
        return SessionInfo(
            id=session.id,
            title=session.title,
            model=session.model,
            workdir=session.workdir,
            message_count=len(session.messages),
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    async def list_sessions(self, limit: int = 20) -> list[SessionInfo]:
        """List recent sessions."""
        store = self._get_session_store()
        sessions = store.list_sessions(limit=limit)
        return [
            SessionInfo(
                id=s.id,
                title=s.title,
                model=s.model,
                workdir=s.workdir,
                message_count=len(s.messages),
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in sessions
        ]

    async def get_session(self, session_id: str) -> SessionDetail:
        """Get session with messages."""
        store = self._get_session_store()
        session = store.get_session(session_id)
        if not session:
            raise CodyNotFoundError(
                f"Session not found: {session_id}",
                code="SESSION_NOT_FOUND",
            )
        return SessionDetail(
            id=session.id,
            title=session.title,
            model=session.model,
            workdir=session.workdir,
            message_count=len(session.messages),
            created_at=session.created_at,
            updated_at=session.updated_at,
            messages=[
                {"role": m.role, "content": m.content, "timestamp": m.timestamp}
                for m in session.messages
            ],
        )

    async def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        store = self._get_session_store()
        deleted = store.delete_session(session_id)
        if not deleted:
            raise CodyNotFoundError(
                f"Session not found: {session_id}",
                code="SESSION_NOT_FOUND",
            )

    # ── Skills ───────────────────────────────────────────────────────────────

    async def list_skills(self) -> list[dict]:
        """List available skills."""
        sm = SkillManager(config=self._get_config(), workdir=self.workdir)
        return [
            {
                "name": s.name,
                "description": s.description,
                "source": s.source,
                "enabled": s.enabled,
            }
            for s in sm.list_skills()
        ]

    async def get_skill(self, skill_name: str) -> dict:
        """Get skill details including full documentation."""
        sm = SkillManager(config=self._get_config(), workdir=self.workdir)
        skill = sm.get_skill(skill_name)
        if not skill:
            raise CodyNotFoundError(
                f"Skill not found: {skill_name}",
                code="SKILL_NOT_FOUND",
            )
        return {
            "name": skill.name,
            "description": skill.description,
            "source": skill.source,
            "enabled": skill.enabled,
            "documentation": skill.documentation,
        }


# ── Sync client ──────────────────────────────────────────────────────────────


def _run_async(coro):
    """Run an async coroutine from sync context."""
    try:
        asyncio.get_running_loop()
        # Already in an event loop — use a thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


class CodyClient:
    """Synchronous Python SDK for Cody — wraps AsyncCodyClient.

    Args:
        workdir: Working directory. Defaults to cwd.
        model: Override model.
        db_path: Path for session database.
    """

    def __init__(
        self,
        workdir: Optional[str] = None,
        *,
        model: Optional[str] = None,
        db_path: Optional[str] = None,
    ):
        self._async = AsyncCodyClient(workdir=workdir, model=model, db_path=db_path)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        _run_async(self._async.close())

    def health(self) -> dict:
        """Return SDK health info."""
        return _run_async(self._async.health())

    def run(
        self,
        prompt: str,
        *,
        workdir: Optional[str] = None,
        model: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> RunResult:
        """Run agent with prompt."""
        return _run_async(self._async.run(prompt, workdir=workdir, model=model, session_id=session_id))

    def stream(
        self,
        prompt: str,
        *,
        workdir: Optional[str] = None,
        model: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        """Stream agent response. Returns list of StreamChunks (sync version)."""
        async def _collect():
            chunks = []
            async for chunk in self._async.stream(prompt, workdir=workdir, model=model, session_id=session_id):
                chunks.append(chunk)
            return chunks
        return _run_async(_collect())

    def tool(
        self,
        tool_name: str,
        params: Optional[dict] = None,
        *,
        workdir: Optional[str] = None,
    ) -> ToolResult:
        """Call a tool directly."""
        return _run_async(self._async.tool(tool_name, params, workdir=workdir))

    def create_session(
        self,
        title: str = "New session",
        model: str = "",
        workdir: str = "",
    ) -> SessionInfo:
        """Create a new session."""
        return _run_async(self._async.create_session(title=title, model=model, workdir=workdir))

    def list_sessions(self, limit: int = 20) -> list[SessionInfo]:
        """List recent sessions."""
        return _run_async(self._async.list_sessions(limit=limit))

    def get_session(self, session_id: str) -> SessionDetail:
        """Get session with messages."""
        return _run_async(self._async.get_session(session_id))

    def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        return _run_async(self._async.delete_session(session_id))

    def list_skills(self) -> list[dict]:
        """List available skills."""
        return _run_async(self._async.list_skills())

    def get_skill(self, skill_name: str) -> dict:
        """Get skill details including full documentation."""
        return _run_async(self._async.get_skill(skill_name))
