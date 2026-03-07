"""Cody SDK - Enhanced client with Builder pattern, events, and metrics.

This module wraps core directly (AgentRunner + SessionStore) and adds:
- Builder pattern construction
- Convenience methods for common operations
- Event hooks for monitoring
- Metrics collection
"""

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Optional

from .config import SDKConfig, config as make_config
from .errors import (
    CodyConfigError,
    CodyNotFoundError,
    CodyToolError,
)
from .events import (
    EventManager,
    EventType,
    RunEvent,
    StreamEvent as SDKStreamEvent,
    ThinkingEvent as SDKThinkingEvent,
    ToolEvent,
)
from .metrics import MetricsCollector, TokenUsage
from .types import (
    RunResult,
    SessionDetail,
    SessionInfo,
    StreamChunk,
    ToolResult,
    _event_to_chunk,
    _usage_from_result,
)


# ── Builder Pattern ─────────────────────────────────────────────────────────


@dataclass
class CodyBuilder:
    """Builder for creating AsyncCodyClient instances.

    Usage:
        client = (
            Cody()
            .workdir("/path/to/project")
            .model("your-model-name")
            .base_url("https://api.example.com/v1")
            .build()
        )
    """

    _workdir: Optional[str] = None
    _model: Optional[str] = None
    _api_key: Optional[str] = None
    _base_url: Optional[str] = None
    _enable_thinking: bool = False
    _thinking_budget: Optional[int] = None
    _permissions: dict = field(default_factory=dict)
    _allowed_roots: list[str] = field(default_factory=list)
    _db_path: Optional[str] = None
    _enable_metrics: bool = False
    _enable_events: bool = False
    _mcp_servers: list[dict] = field(default_factory=list)
    _lsp_languages: list[str] = field(default_factory=lambda: ["python", "typescript", "go"])
    _event_handlers: list[tuple] = field(default_factory=list)

    def workdir(self, path: str) -> "CodyBuilder":
        """Set working directory."""
        self._workdir = path
        return self

    def model(self, model: str) -> "CodyBuilder":
        """Set model name (e.g., 'claude-sonnet-4-0', 'gpt-4o')."""
        self._model = model
        return self

    def api_key(self, key: str) -> "CodyBuilder":
        """Set API key."""
        self._api_key = key
        return self

    def base_url(self, url: str) -> "CodyBuilder":
        """Set custom API base URL."""
        self._base_url = url
        return self

    def thinking(self, enabled: bool = True, budget: Optional[int] = None) -> "CodyBuilder":
        """Enable thinking mode with optional token budget."""
        self._enable_thinking = enabled
        if budget:
            self._thinking_budget = budget
        return self

    def permission(self, tool: str, level: str) -> "CodyBuilder":
        """Set permission for a specific tool."""
        self._permissions[tool] = level
        return self

    def allowed_root(self, path: str) -> "CodyBuilder":
        """Add an allowed root path for file operations."""
        self._allowed_roots.append(path)
        return self

    def allowed_roots(self, paths: list[str]) -> "CodyBuilder":
        """Set multiple allowed root paths."""
        self._allowed_roots = paths
        return self

    def db_path(self, path: str) -> "CodyBuilder":
        """Set session database path."""
        self._db_path = path
        return self

    def enable_metrics(self) -> "CodyBuilder":
        """Enable metrics collection."""
        self._enable_metrics = True
        return self

    def enable_events(self) -> "CodyBuilder":
        """Enable event system."""
        self._enable_events = True
        return self

    def mcp_server(self, server: dict) -> "CodyBuilder":
        """Add MCP server configuration."""
        self._mcp_servers.append(server)
        return self

    def lsp_languages(self, languages: list[str]) -> "CodyBuilder":
        """Set LSP languages to enable."""
        self._lsp_languages = languages
        return self

    def on(self, event_type: str, handler) -> "CodyBuilder":
        """Register event handler. Implicitly enables events.

        Args:
            event_type: Event type string, e.g. "tool_call", "tool_result".
            handler: Callback function that receives the event.
        """
        self._enable_events = True
        self._event_handlers.append((event_type, handler))
        return self

    def build(self) -> "AsyncCodyClient":
        """Build and return the client instance."""
        cfg = make_config(
            model=self._model,
            workdir=self._workdir,
            api_key=self._api_key,
            base_url=self._base_url,
            enable_thinking=self._enable_thinking,
            thinking_budget=self._thinking_budget,
            permissions=self._permissions,
            allowed_roots=self._allowed_roots,
            db_path=self._db_path,
            enable_metrics=self._enable_metrics,
            enable_events=self._enable_events,
        )
        cfg.mcp.servers = self._mcp_servers
        cfg.lsp.languages = self._lsp_languages
        client = AsyncCodyClient(config=cfg)
        # Apply deferred event handlers
        for event_type_str, handler in self._event_handlers:
            client.on(event_type_str, handler)
        return client


def Cody() -> CodyBuilder:
    """Create a new CodyBuilder instance.

    Usage:
        client = Cody().workdir(".").model("your-model-name").base_url("https://api.example.com/v1").build()
    """
    return CodyBuilder()


# ── Async Client (wraps core directly) ───────────────────────────────────────


class AsyncCodyClient:
    """Async Python SDK for Cody — wraps core engine directly.

    Supports three construction styles:
        # 1. Builder (recommended)
        client = Cody().workdir(".").model("...").build()

        # 2. Direct parameters
        client = AsyncCodyClient(workdir=".", model="...")

        # 3. Config object
        client = AsyncCodyClient(config=cfg)

    Enhanced features (vs. bare core):
        - Event hooks via on() / on_async()
        - Metrics collection
        - Convenience methods (read_file, write_file, etc.)
        - Rich error hierarchy
    """

    def __init__(
        self,
        config: Optional[SDKConfig] = None,
        workdir: Optional[str] = None,
        *,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        db_path: Optional[str] = None,
        enable_metrics: bool = False,
        enable_events: bool = False,
    ):
        if config:
            self._config = config
        else:
            self._config = make_config(
                model=model,
                workdir=workdir,
                api_key=api_key,
                base_url=base_url,
                db_path=db_path,
                enable_metrics=enable_metrics,
                enable_events=enable_events,
            )

        self.workdir = Path(self._config.workdir) if self._config.workdir else Path.cwd()
        # Only override model if the user explicitly provided one
        self._model_override = (
            self._config.model.model if self._config.model.model else None
        )
        self._db_path = Path(self._config.db_path) if self._config.db_path else None

        # Core objects (lazy-initialized)
        self._runner = None
        self._session_store = None
        self._core_config = None

        # Enhanced features
        self._metrics: Optional[MetricsCollector] = None
        self._events: Optional[EventManager] = None

        if self._config.enable_metrics:
            self._metrics = MetricsCollector()
        if self._config.enable_events:
            self._events = EventManager()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    # ── Internal: core access ─────────────────────────────────────────────

    def _get_config(self):
        """Get or create core Config."""
        if self._core_config is None:
            from ..core.config import Config
            self._core_config = Config.load(workdir=self.workdir)
            if self._model_override:
                self._core_config.model = self._model_override
            if self._config.model.enable_thinking:
                self._core_config.enable_thinking = True
                if self._config.model.thinking_budget:
                    self._core_config.thinking_budget = self._config.model.thinking_budget
            if self._config.model.api_key:
                self._core_config.model_api_key = self._config.model.api_key
            if self._config.model.base_url:
                self._core_config.model_base_url = self._config.model.base_url
        return self._core_config

    def _get_runner(self):
        """Get or create AgentRunner."""
        if self._runner is None:
            from ..core.runner import AgentRunner
            self._runner = AgentRunner(config=self._get_config(), workdir=self.workdir)
        return self._runner

    def _get_session_store(self):
        """Get or create SessionStore."""
        if self._session_store is None:
            from ..core.session import SessionStore
            self._session_store = SessionStore(db_path=self._db_path)
        return self._session_store

    async def close(self):
        """Clean up resources."""
        if self._runner:
            await self._runner.stop_mcp()
            await self._runner.stop_lsp()
            self._runner = None

    # ── Health ────────────────────────────────────────────────────────────

    async def health(self) -> dict:
        """Return SDK health info."""
        from .. import __version__
        return {"status": "ok", "version": __version__}

    # ── Run ───────────────────────────────────────────────────────────────

    async def run(
        self,
        prompt,
        *,
        session_id: Optional[str] = None,
        stream: bool = False,
    ):
        """Run agent with prompt.

        Args:
            prompt: Task description (str or Prompt).
            session_id: Optional session ID for multi-turn.
            stream: If True, return async iterator of StreamChunk.

        Returns:
            RunResult if stream=False, else AsyncIterator[StreamChunk].
        """
        # Fire event
        if self._events:
            await self._events.dispatch_async(RunEvent(
                event_type=EventType.RUN_START,
                prompt=str(prompt),
                session_id=session_id,
            ))

        # Start metrics
        if self._metrics:
            self._metrics.start_run(
                str(prompt), session_id, self._config.model.enable_thinking
            )

        try:
            if stream:
                return self._stream_run(prompt, session_id)

            runner = self._get_runner()
            # Always use session to enable multi-turn by default
            store = self._get_session_store()
            result, sid = await runner.run_with_session(prompt, store, session_id)

            run_result = RunResult(
                output=result.output,
                session_id=sid,
                usage=_usage_from_result(result),
                thinking=result.thinking,
            )

            # Record metrics
            if self._metrics:
                self._metrics.end_run(
                    result.output,
                    TokenUsage(
                        input_tokens=run_result.usage.input_tokens,
                        output_tokens=run_result.usage.output_tokens,
                        total_tokens=run_result.usage.total_tokens,
                    ),
                )

            # Fire tool events from traces
            if self._events and result.tool_traces:
                for trace in result.tool_traces:
                    await self._events.dispatch_async(ToolEvent(
                        event_type=EventType.TOOL_CALL,
                        tool_name=trace.tool_name,
                        args=trace.args,
                    ))
                    await self._events.dispatch_async(ToolEvent(
                        event_type=EventType.TOOL_RESULT,
                        tool_name=trace.tool_name,
                        result=trace.result,
                    ))

            # Fire run end event
            if self._events:
                await self._events.dispatch_async(RunEvent(
                    event_type=EventType.RUN_END,
                    prompt=str(prompt),
                    session_id=session_id,
                    result=result.output,
                ))

            return run_result

        except Exception as e:
            # Ensure metrics run is closed on exception
            if self._metrics and self._metrics._current_run is not None:
                self._metrics.end_run("", TokenUsage(0, 0, 0))
            if self._events:
                await self._events.dispatch_async(RunEvent(
                    event_type=EventType.RUN_ERROR,
                    prompt=str(prompt),
                    session_id=session_id,
                    error=str(e),
                ))
            raise

    async def stream(
        self,
        prompt,
        *,
        session_id: Optional[str] = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream agent response. Yields StreamChunk objects."""
        runner = self._get_runner()

        if session_id:
            store = self._get_session_store()
            async for event, sid in runner.run_stream_with_session(
                prompt, store, session_id
            ):
                yield _event_to_chunk(event, sid)
        else:
            async for event in runner.run_stream(prompt):
                yield _event_to_chunk(event)

    # Alias for stream() — matches the name used in demos/docs
    run_stream = stream

    async def _stream_run(self, prompt, session_id: Optional[str] = None):
        """Internal streaming run (called when run(stream=True))."""
        async for chunk in self.stream(prompt, session_id=session_id):
            if self._events:
                if chunk.type == "thinking":
                    await self._events.dispatch_async(SDKThinkingEvent(
                        event_type=EventType.THINKING_CHUNK,
                        content=chunk.content,
                    ))
                elif chunk.type == "tool_call":
                    await self._events.dispatch_async(ToolEvent(
                        event_type=EventType.TOOL_CALL,
                        tool_name=chunk.tool_name or chunk.content,
                        args=chunk.args or {},
                    ))
                elif chunk.type == "tool_result":
                    await self._events.dispatch_async(ToolEvent(
                        event_type=EventType.TOOL_RESULT,
                        tool_name=chunk.tool_name or "",
                        result=chunk.content,
                    ))
                elif chunk.type == "text_delta":
                    await self._events.dispatch_async(SDKStreamEvent(
                        event_type=EventType.STREAM_CHUNK,
                        chunk_type=chunk.type,
                        content=chunk.content,
                    ))
            yield chunk

    # ── Tool ──────────────────────────────────────────────────────────────

    async def tool(
        self,
        tool_name: str,
        params: Optional[dict] = None,
        *,
        workdir: Optional[str] = None,
    ) -> ToolResult:
        """Call a tool directly."""
        from ..core import tools
        from ..core.config import Config
        from ..core.deps import CodyDeps, ToolContext
        from ..core.skill_manager import SkillManager

        tool_func = getattr(tools, tool_name, None)
        if not tool_func:
            raise CodyNotFoundError(
                f"Tool not found: {tool_name}",
                code="TOOL_NOT_FOUND",
            )

        if self._events:
            await self._events.dispatch_async(ToolEvent(
                event_type=EventType.TOOL_CALL,
                tool_name=tool_name,
                args=params or {},
            ))

        effective_workdir = Path(workdir) if workdir else self.workdir
        cfg = Config.load(workdir=effective_workdir)
        sm = SkillManager(config=cfg, workdir=effective_workdir)
        deps = CodyDeps(
            config=cfg,
            workdir=effective_workdir,
            skill_manager=sm,
            allowed_roots=[effective_workdir],
        )

        start_time = time.time()
        try:
            result_str = await tool_func(ToolContext(deps), **(params or {}))
            duration = time.time() - start_time

            if self._metrics:
                self._metrics.record_tool_call(tool_name, duration, success=True)
            if self._events:
                await self._events.dispatch_async(ToolEvent(
                    event_type=EventType.TOOL_RESULT,
                    tool_name=tool_name,
                    args=params or {},
                    result=result_str[:500] if result_str else "",
                    duration=duration,
                ))
            return ToolResult(result=result_str)

        except Exception as e:
            duration = time.time() - start_time
            if self._metrics:
                self._metrics.record_tool_call(
                    tool_name, duration, success=False, error=str(e)
                )
            if self._events:
                await self._events.dispatch_async(ToolEvent(
                    event_type=EventType.TOOL_ERROR,
                    tool_name=tool_name,
                    args=params or {},
                    error=str(e),
                    duration=duration,
                ))
            raise CodyToolError(str(e), tool_name=tool_name) from e

    # ── Sessions ──────────────────────────────────────────────────────────

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
        info = SessionInfo(
            id=session.id,
            title=session.title,
            model=session.model,
            workdir=session.workdir,
            message_count=len(session.messages),
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

        if self._events:
            from .events import SessionEvent
            await self._events.dispatch_async(SessionEvent(
                event_type=EventType.SESSION_CREATE,
                session_id=session.id,
                title=title,
            ))

        return info

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

    async def get_latest_session(
        self,
        workdir: str | None = None,
    ) -> SessionInfo | None:
        """Get the most recent session, optionally filtered by workdir."""
        store = self._get_session_store()
        session = store.get_latest_session(workdir=workdir)
        if not session:
            return None
        return SessionInfo(
            id=session.id,
            title=session.title,
            model=session.model,
            workdir=session.workdir,
            message_count=len(session.messages),
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    def get_message_count(self, session_id: str) -> int:
        """Get message count for a session."""
        store = self._get_session_store()
        return store.get_message_count(session_id)

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Add a message to a session."""
        store = self._get_session_store()
        store.add_message(session_id, role, content)

    def update_title(self, session_id: str, title: str) -> None:
        """Update session title."""
        store = self._get_session_store()
        store.update_title(session_id, title)

    @staticmethod
    def messages_to_history(messages) -> list:
        """Convert stored session messages to pydantic-ai message format."""
        from ..core.runner import AgentRunner
        return AgentRunner.messages_to_history(messages)

    # ── Skills ────────────────────────────────────────────────────────────

    async def list_skills(self) -> list[dict]:
        """List available skills."""
        from ..core.skill_manager import SkillManager
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
        from ..core.skill_manager import SkillManager
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

    # ── Convenience Methods ──────────────────────────────────────────────

    async def read_file(self, path: str) -> str:
        """Read a file."""
        result = await self.tool("read_file", {"path": path})
        return result.result

    async def write_file(self, path: str, content: str) -> str:
        """Write a file."""
        result = await self.tool("write_file", {"path": path, "content": content})
        return result.result

    async def edit_file(self, path: str, old_text: str, new_text: str) -> str:
        """Edit a file."""
        result = await self.tool("edit_file", {
            "path": path, "old_text": old_text, "new_text": new_text,
        })
        return result.result

    async def list_directory(self, path: str = ".") -> str:
        """List directory contents."""
        result = await self.tool("list_directory", {"path": path})
        return result.result

    async def grep(self, pattern: str, include: str = "*") -> str:
        """Search for pattern in files."""
        result = await self.tool("grep", {"pattern": pattern, "include": include})
        return result.result

    async def glob(self, pattern: str) -> str:
        """Find files by glob pattern."""
        result = await self.tool("glob", {"pattern": pattern})
        return result.result

    async def exec_command(self, command: str) -> str:
        """Execute shell command."""
        result = await self.tool("exec_command", {"command": command})
        return result.result

    async def search_files(self, query: str) -> str:
        """Search for files by name (fuzzy)."""
        result = await self.tool("search_files", {"query": query})
        return result.result

    # ── LSP Methods ──────────────────────────────────────────────────────

    async def lsp_diagnostics(self, file_path: str) -> str:
        """Get LSP diagnostics for a file."""
        result = await self.tool("lsp_diagnostics", {"file_path": file_path})
        return result.result

    async def lsp_definition(self, file_path: str, line: int, column: int) -> str:
        """Go to definition."""
        result = await self.tool("lsp_definition", {
            "file_path": file_path, "line": line, "character": column,
        })
        return result.result

    async def lsp_references(self, file_path: str, line: int, column: int) -> str:
        """Find references."""
        result = await self.tool("lsp_references", {
            "file_path": file_path, "line": line, "character": column,
        })
        return result.result

    async def lsp_hover(self, file_path: str, line: int, column: int) -> str:
        """Get hover info."""
        result = await self.tool("lsp_hover", {
            "file_path": file_path, "line": line, "character": column,
        })
        return result.result

    # ── Event Methods ────────────────────────────────────────────────────

    def on(self, event_type, handler):
        """Register event handler.

        Args:
            event_type: EventType enum or string (e.g. "tool_call").
            handler: Callback function.
        """
        if not self._events:
            raise CodyConfigError("Events not enabled. Use enable_events() in config.")
        if isinstance(event_type, str):
            event_type = EventType(event_type)
        self._events.register(event_type, handler)

    def on_async(self, event_type, handler):
        """Register async event handler.

        Args:
            event_type: EventType enum or string (e.g. "tool_call").
            handler: Callback function.
        """
        if not self._events:
            raise CodyConfigError("Events not enabled. Use enable_events() in config.")
        if isinstance(event_type, str):
            event_type = EventType(event_type)
        self._events.register_async(event_type, handler)

    # ── Metrics Methods ──────────────────────────────────────────────────

    def get_metrics(self) -> Optional[dict]:
        """Get metrics summary."""
        if not self._metrics:
            return None
        return self._metrics.get_summary()

    def get_metrics_collector(self) -> Optional[MetricsCollector]:
        """Get metrics collector instance."""
        return self._metrics


# ── Sync Client ──────────────────────────────────────────────────────────────


def _run_async(coro):
    """Run an async coroutine from sync context."""
    try:
        asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


class CodyClient:
    """Synchronous Python SDK for Cody — wraps AsyncCodyClient.

    Usage:
        with CodyClient(workdir=".") as client:
            result = client.run("task")
    """

    def __init__(self, **kwargs):
        self._async = AsyncCodyClient(**kwargs)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        _run_async(self._async.close())

    def health(self) -> dict:
        return _run_async(self._async.health())

    def run(self, prompt, *, session_id: Optional[str] = None):
        return _run_async(self._async.run(prompt, session_id=session_id))

    def stream(self, prompt, *, session_id: Optional[str] = None):
        """Collect all stream chunks (sync version returns list)."""
        async def _collect():
            chunks = []
            async for chunk in self._async.stream(prompt, session_id=session_id):
                chunks.append(chunk)
            return chunks
        return _run_async(_collect())

    # Alias
    run_stream = stream

    def tool(self, tool_name: str, params: Optional[dict] = None, **kwargs):
        return _run_async(self._async.tool(tool_name, params, **kwargs))

    def create_session(self, title: str = "New session", **kwargs):
        return _run_async(self._async.create_session(title=title, **kwargs))

    def list_sessions(self, limit: int = 20):
        return _run_async(self._async.list_sessions(limit=limit))

    def get_session(self, session_id: str):
        return _run_async(self._async.get_session(session_id))

    def delete_session(self, session_id: str):
        return _run_async(self._async.delete_session(session_id))

    def list_skills(self):
        return _run_async(self._async.list_skills())

    def get_skill(self, skill_name: str):
        return _run_async(self._async.get_skill(skill_name))

    def get_latest_session(self, workdir: str | None = None):
        return _run_async(self._async.get_latest_session(workdir=workdir))

    def get_message_count(self, session_id: str) -> int:
        return self._async.get_message_count(session_id)

    def add_message(self, session_id: str, role: str, content: str) -> None:
        self._async.add_message(session_id, role, content)

    def update_title(self, session_id: str, title: str) -> None:
        self._async.update_title(session_id, title)

    @staticmethod
    def messages_to_history(messages) -> list:
        return AsyncCodyClient.messages_to_history(messages)

    def read_file(self, path: str) -> str:
        return _run_async(self._async.read_file(path))

    def write_file(self, path: str, content: str) -> str:
        return _run_async(self._async.write_file(path, content))

    def get_metrics(self) -> Optional[dict]:
        return self._async.get_metrics()
