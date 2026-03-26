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
from typing import AsyncIterator, Literal, Optional, overload

from .config import (
    CircuitBreakerConfig as SDKCircuitBreakerConfig,
    InteractionConfig as SDKInteractionConfig,
    MCPServerConfig as SDKMCPServerConfig,
    SDKConfig,
    config as make_config,
)
from .errors import (
    CodyConfigError,
    CodyNotFoundError,
    CodyToolError,
)
from .events import (
    ContextCompactEvent as SDKContextCompactEvent,
    EventManager,
    EventType,
    ModelEvent,
    RunEvent,
    SessionEvent,
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


_BUILDER_UNSET = object()  # sentinel: "not set" vs explicit None


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
    _strict_read_boundary: bool = False
    _db_path: Optional[str] = None
    _enable_metrics: bool = False
    _enable_events: bool = False
    _mcp_servers: list[dict | SDKMCPServerConfig] = field(default_factory=list)
    _auto_start_mcp: bool = False
    _interaction: SDKInteractionConfig | None = None
    _circuit_breaker: SDKCircuitBreakerConfig | None = None
    _skill_dirs: list[str] = field(default_factory=list)
    _lsp_languages: list[str] = field(default_factory=lambda: ["python", "typescript", "go"])
    _event_handlers: list[tuple] = field(default_factory=list)
    _custom_tools: list = field(default_factory=list)
    _system_prompt: str | None = None
    _extra_system_prompt: str | None = None
    _before_tool_hooks: list = field(default_factory=list)
    _after_tool_hooks: list = field(default_factory=list)
    _session_store: object | None = None
    _audit_logger: object | None = None
    _file_history: object | None = None
    _memory_store: object | None = _BUILDER_UNSET
    _stateless: bool = False

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

    def strict_read_boundary(self, enabled: bool = True) -> "CodyBuilder":
        """When True, read operations are also restricted to workdir + allowed_roots."""
        self._strict_read_boundary = enabled
        return self

    def skill_dir(self, path: str) -> "CodyBuilder":
        """Add a custom skill directory."""
        self._skill_dirs.append(path)
        return self

    def skill_dirs(self, paths: list[str]) -> "CodyBuilder":
        """Set custom skill directories."""
        self._skill_dirs = list(paths)
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

    def interaction(
        self,
        enabled: bool = True,
        timeout: float = 30.0,
    ) -> "CodyBuilder":
        """Configure human-in-the-loop interaction.

        When enabled, the runner pauses on interaction requests (e.g. the
        ``question`` tool) and waits for a human response via
        ``submit_interaction()``.  If no response arrives within *timeout*
        seconds, the run is terminated with an ``InteractionTimeoutEvent``.

        Only effective with async methods (``run()`` / ``stream()``).
        ``run_sync()`` always auto-approves regardless of this setting.

            Cody().interaction(enabled=True, timeout=30).build()
        """
        self._interaction = SDKInteractionConfig(enabled=enabled, timeout=timeout)
        return self

    def circuit_breaker(
        self,
        config: SDKCircuitBreakerConfig | None = None,
        *,
        enabled: bool = True,
        max_tokens: int = 200_000,
        max_cost_usd: float = 5.0,
        max_steps: int = 0,
        loop_detect_turns: int = 6,
        loop_similarity_threshold: float = 0.9,
        model_prices: dict[str, float] | None = None,
    ) -> "CodyBuilder":
        """Configure circuit breaker for automatic run termination.

        Accepts either a CircuitBreakerConfig object or keyword arguments:

            # Option A: config object
            Cody().circuit_breaker(CircuitBreakerConfig(max_cost_usd=10.0)).build()

            # Option B: keyword arguments
            Cody().circuit_breaker(max_cost_usd=10.0, max_steps=50).build()
        """
        if config is not None:
            self._circuit_breaker = config
        else:
            self._circuit_breaker = SDKCircuitBreakerConfig(
                enabled=enabled,
                max_tokens=max_tokens,
                max_cost_usd=max_cost_usd,
                max_steps=max_steps,
                loop_detect_turns=loop_detect_turns,
                loop_similarity_threshold=loop_similarity_threshold,
                model_prices=model_prices or {},
            )
        return self

    def mcp_server(self, server: dict | SDKMCPServerConfig) -> "CodyBuilder":
        """Add MCP server configuration (dict or MCPServerConfig)."""
        self._mcp_servers.append(server)
        return self

    def mcp_stdio_server(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> "CodyBuilder":
        """Add a stdio-based MCP server (subprocess)."""
        self._mcp_servers.append(SDKMCPServerConfig(
            name=name, transport='stdio',
            command=command, args=args or [], env=env or {},
        ))
        return self

    def mcp_http_server(
        self,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> "CodyBuilder":
        """Add an HTTP-based MCP server (remote endpoint)."""
        self._mcp_servers.append(SDKMCPServerConfig(
            name=name, transport='http',
            url=url, headers=headers or {},
        ))
        return self

    def auto_start_mcp(self, enabled: bool = True) -> "CodyBuilder":
        """Auto-start MCP servers on first run(). Default is False."""
        self._auto_start_mcp = enabled
        return self

    def lsp_languages(self, languages: list[str]) -> "CodyBuilder":
        """Set LSP languages to enable."""
        self._lsp_languages = languages
        return self

    def tool(self, func) -> "CodyBuilder":
        """Register a custom tool function.

        The function must be an async callable with the signature::

            async def my_tool(ctx: RunContext[CodyDeps], arg: str) -> str:
                ...

        Custom tools are registered alongside built-in tools and are
        available to the agent during ``run()`` / ``stream()`` calls.

        Example::

            async def lookup_jira(ctx: RunContext[CodyDeps], ticket: str) -> str:
                \"\"\"Look up a Jira ticket by ID.\"\"\"
                return await fetch_jira(ticket)

            client = Cody().tool(lookup_jira).build()
        """
        self._custom_tools.append(func)
        return self

    def system_prompt(self, text: str) -> "CodyBuilder":
        """Replace the default base persona with a custom system prompt.

        The custom prompt replaces only the base persona. CODY.md project
        instructions, project memory, and skills are still appended.

        Example::

            client = (
                Cody()
                .system_prompt("You are a security-focused code review agent.")
                .build()
            )
        """
        self._system_prompt = text
        return self

    def extra_system_prompt(self, text: str) -> "CodyBuilder":
        """Append additional instructions after all built-in system prompt parts.

        Unlike ``system_prompt()``, this does not replace the default persona
        — it adds to it.  Use this for injecting business context or
        run-specific instructions.

        Example::

            client = (
                Cody()
                .extra_system_prompt("Always respond in Chinese.")
                .build()
            )
        """
        self._extra_system_prompt = text
        return self

    def before_tool(self, hook) -> "CodyBuilder":
        """Register a before-tool hook.

        The hook is called before every tool execution with the signature::

            async def my_hook(tool_name: str, args: dict) -> dict | None:
                ...

        Return the (possibly modified) args dict to proceed, or ``None``
        to reject the call (the model will see a retry message).

        Example::

            async def log_calls(tool_name, args):
                print(f"Calling {tool_name}")
                return args  # proceed unchanged

            client = Cody().before_tool(log_calls).build()
        """
        self._before_tool_hooks.append(hook)
        return self

    def after_tool(self, hook) -> "CodyBuilder":
        """Register an after-tool hook.

        The hook is called after every tool execution with the signature::

            async def my_hook(tool_name: str, args: dict, result: str) -> str:
                ...

        Return the (possibly modified) result string.

        Example::

            async def redact_secrets(tool_name, args, result):
                return result.replace(os.environ["SECRET"], "***")

            client = Cody().after_tool(redact_secrets).build()
        """
        self._after_tool_hooks.append(hook)
        return self

    def session_store(self, store) -> "CodyBuilder":
        """Inject a custom session store (must satisfy SessionStoreProtocol)."""
        self._session_store = store
        return self

    def audit_logger(self, logger) -> "CodyBuilder":
        """Inject a custom audit logger (must satisfy AuditLoggerProtocol)."""
        self._audit_logger = logger
        return self

    def file_history(self, history) -> "CodyBuilder":
        """Inject a custom file history (must satisfy FileHistoryProtocol)."""
        self._file_history = history
        return self

    def memory_store(self, store) -> "CodyBuilder":
        """Inject a custom memory store (must satisfy MemoryStoreProtocol)."""
        self._memory_store = store
        return self

    def stateless(self) -> "CodyBuilder":
        """Enable stateless mode — no persistence (session, audit, file history, memory).

        Uses null storage implementations so the code path stays the same
        but nothing is written to disk. Individual storage can still be
        overridden after calling stateless() (e.g. ``.stateless().audit_logger(real_logger)``).
        """
        self._stateless = True
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
            strict_read_boundary=self._strict_read_boundary,
            db_path=self._db_path,
            enable_metrics=self._enable_metrics,
            enable_events=self._enable_events,
        )
        if self._interaction is not None:
            cfg.interaction = self._interaction
        if self._circuit_breaker is not None:
            cfg.circuit_breaker = self._circuit_breaker
        cfg.skill_dirs = self._skill_dirs
        cfg.mcp.servers = self._mcp_servers
        cfg.lsp.languages = self._lsp_languages
        # Apply stateless defaults for any storage not explicitly set
        session_store = self._session_store
        audit_logger = self._audit_logger
        file_history = self._file_history
        memory_store = self._memory_store
        if self._stateless:
            from ..core.storage import (
                NullSessionStore, NullAuditLogger,
                NullFileHistory, NullMemoryStore,
            )
            if session_store is None:
                session_store = NullSessionStore()
            if audit_logger is None:
                audit_logger = NullAuditLogger()
            if file_history is None:
                file_history = NullFileHistory()
            if memory_store is _BUILDER_UNSET:
                memory_store = NullMemoryStore()

        client = AsyncCodyClient(
            config=cfg,
            auto_start_mcp=self._auto_start_mcp,
            custom_tools=self._custom_tools or None,
            system_prompt=self._system_prompt,
            extra_system_prompt=self._extra_system_prompt,
            before_tool_hooks=self._before_tool_hooks or None,
            after_tool_hooks=self._after_tool_hooks or None,
            session_store=session_store,
            audit_logger=audit_logger,
            file_history=file_history,
            memory_store=memory_store,
        )
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
        auto_start_mcp: bool = False,
        custom_tools: list | None = None,
        system_prompt: str | None = None,
        extra_system_prompt: str | None = None,
        before_tool_hooks: list | None = None,
        after_tool_hooks: list | None = None,
        session_store: object | None = None,
        audit_logger: object | None = None,
        file_history: object | None = None,
        memory_store: object | None = _BUILDER_UNSET,
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

        # Custom tools (user-defined async functions)
        self._custom_tools: list = custom_tools or []

        # Custom system prompt overrides
        self._system_prompt: str | None = system_prompt
        self._extra_system_prompt: str | None = extra_system_prompt

        # Step hooks
        self._before_tool_hooks: list = before_tool_hooks or []
        self._after_tool_hooks: list = after_tool_hooks or []

        # Storage layer injection (None = use defaults, _BUILDER_UNSET = not set)
        self._injected_session_store = session_store
        self._injected_audit_logger = audit_logger
        self._injected_file_history = file_history
        self._injected_memory_store = memory_store

        # MCP auto-start flag
        self._auto_start_mcp = auto_start_mcp
        self._mcp_started = False

        # LSP auto-start: start configured language servers on first run
        self._lsp_started = False

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

    # ── Core access ──────────────────────────────────────────────────────

    def _get_config(self):
        """Get or create core Config."""
        if self._core_config is None:
            from ..core.config import Config, MCPServerConfig as CoreMCPServerConfig
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
            # Apply security config from SDK
            if self._config.security.allowed_roots:
                self._core_config.security.allowed_roots = self._config.security.allowed_roots
            if self._config.security.strict_read_boundary:
                self._core_config.security.strict_read_boundary = True
            if self._config.security.blocked_commands:
                self._core_config.security.blocked_commands = self._config.security.blocked_commands
            # Apply custom skill directories from SDK config
            if self._config.skill_dirs:
                existing = set(self._core_config.skills.custom_dirs)
                for d in self._config.skill_dirs:
                    if d not in existing:
                        self._core_config.skills.custom_dirs.append(d)
                        existing.add(d)
            # Apply interaction config from SDK
            if self._config.interaction.enabled:
                from ..core.config import InteractionConfig as CoreIAConfig
                self._core_config.interaction = CoreIAConfig(
                    enabled=self._config.interaction.enabled,
                    timeout=self._config.interaction.timeout,
                )
            # Apply circuit breaker config from SDK
            from ..core.config import CircuitBreakerConfig as CoreCBConfig
            sdk_cb = self._config.circuit_breaker
            # Default SDKCircuitBreakerConfig values for comparison
            defaults = SDKCircuitBreakerConfig()
            if (sdk_cb.enabled != defaults.enabled
                    or sdk_cb.max_tokens != defaults.max_tokens
                    or sdk_cb.max_cost_usd != defaults.max_cost_usd
                    or sdk_cb.loop_detect_turns != defaults.loop_detect_turns
                    or sdk_cb.loop_similarity_threshold != defaults.loop_similarity_threshold
                    or sdk_cb.model_prices):
                cb_dict = sdk_cb.to_dict()
                # Merge model_prices: core defaults ← SDK overrides
                merged_prices = dict(self._core_config.circuit_breaker.model_prices)
                merged_prices.update(cb_dict.pop("model_prices", {}))
                self._core_config.circuit_breaker = CoreCBConfig(
                    **cb_dict, model_prices=merged_prices,
                )
            # Apply MCP servers from SDK config
            if self._config.mcp.enabled and self._config.mcp.servers:
                for s in self._config.mcp.servers:
                    if isinstance(s, SDKMCPServerConfig):
                        d = s.to_dict()
                    else:
                        d = s
                    self._core_config.mcp.servers.append(CoreMCPServerConfig(**d))
        return self._core_config

    def set_config(self, config) -> None:
        """Apply a pre-built core Config, replacing any cached config/runner.

        This is the public API for CLI/TUI to inject a Config with overrides
        (thinking, extra_roots, etc.) without reaching into private attributes.
        """
        self._core_config = config
        self._runner = None  # Force lazy re-creation with updated config

    def get_runner(self):
        """Get or create the underlying AgentRunner.

        Power-user API for callers that need raw streaming events
        (ToolCallEvent, ThinkingEvent, etc.) or direct MCP control.
        """
        if self._runner is None:
            from ..core.runner import AgentRunner, _UNSET
            # Convert SDK sentinel to runner sentinel
            mem = _UNSET if self._injected_memory_store is _BUILDER_UNSET else self._injected_memory_store
            self._runner = AgentRunner(
                config=self._get_config(),
                workdir=self.workdir,
                custom_tools=self._custom_tools or None,
                system_prompt=self._system_prompt,
                extra_system_prompt=self._extra_system_prompt,
                before_tool_hooks=self._before_tool_hooks or None,
                after_tool_hooks=self._after_tool_hooks or None,
                audit_logger=self._injected_audit_logger,
                file_history=self._injected_file_history,
                memory_store=mem,
            )
        return self._runner

    def get_session_store(self):
        """Get or create the underlying SessionStore.

        Power-user API for callers that need synchronous session access
        (e.g. TUI on_mount) or direct store operations.

        If a custom session store was injected via the builder, it is returned
        directly (must satisfy ``SessionStoreProtocol``).
        """
        if self._session_store is None:
            if self._injected_session_store is not None:
                self._session_store = self._injected_session_store
            else:
                from ..core.session import SessionStore
                self._session_store = SessionStore(db_path=self._db_path)
        return self._session_store

    async def start_mcp(self) -> None:
        """Start MCP servers if configured. Called automatically on first run() when auto_start_mcp=True."""
        runner = self.get_runner()
        if not self._mcp_started:
            await runner.start_mcp()
            self._mcp_started = True

    async def start_lsp(self) -> None:
        """Start LSP servers for configured languages.

        Called automatically on first run()/stream() when lsp.enabled is True
        and lsp.languages is non-empty.  Silently skips languages whose
        server binary is not installed.
        """
        if self._lsp_started:
            return
        self._lsp_started = True
        languages = self._config.lsp.languages if self._config.lsp.enabled else []
        if not languages:
            return
        runner = self.get_runner()
        for lang in languages:
            try:
                await runner.start_lsp(lang)
            except Exception:
                # LSP server not installed — skip silently
                pass

    async def add_mcp_server(
        self,
        name: str,
        *,
        transport: Literal["stdio", "http"] = "stdio",
        command: str = "",
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        url: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        """Dynamically add and start an MCP server at runtime.

        Args:
            name: Server name (used as prefix in tool calls, e.g. "feishu/fetch-doc").
            transport: "stdio" or "http".
            command: Command to run (stdio only).
            args: Command arguments (stdio only).
            env: Environment variables (stdio only).
            url: HTTP endpoint URL (http only).
            headers: HTTP headers (http only).
        """
        from ..core.config import MCPServerConfig as CoreMCPServerConfig

        server_config = CoreMCPServerConfig(
            name=name,
            transport=transport,
            command=command,
            args=args or [],
            env=env or {},
            url=url,
            headers=headers or {},
        )

        runner = self.get_runner()
        # Add to core config so it persists
        runner.config.mcp.servers.append(server_config)
        # Start this single server immediately
        if runner._mcp_client:
            await runner._mcp_client.start_server(server_config)
        else:
            # MCP client not yet created, start full MCP
            await runner.start_mcp()
            self._mcp_started = True

    async def close(self):
        """Clean up resources."""
        if self._runner:
            await self._runner.stop_mcp()
            await self._runner.stop_lsp()
            self._runner = None
        if self._events:
            await self._events.dispatch_async(SessionEvent(
                event_type=EventType.SESSION_CLOSE,
            ))

    # ── Health ────────────────────────────────────────────────────────────

    async def health(self) -> dict:
        """Return SDK health info."""
        from .. import __version__
        return {"status": "ok", "version": __version__}

    # ── Run ───────────────────────────────────────────────────────────────

    @overload
    async def run(
        self, prompt, *, session_id: Optional[str] = None, stream: Literal[False] = False,
        include_tools: list[str] | None = None, exclude_tools: list[str] | None = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> RunResult: ...

    @overload
    async def run(
        self, prompt, *, session_id: Optional[str] = None, stream: Literal[True],
        include_tools: list[str] | None = None, exclude_tools: list[str] | None = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[StreamChunk]: ...

    async def run(
        self,
        prompt,
        *,
        session_id: Optional[str] = None,
        stream: bool = False,
        include_tools: list[str] | None = None,
        exclude_tools: list[str] | None = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> RunResult | AsyncIterator[StreamChunk]:
        """Run agent with prompt.

        Args:
            prompt: Task description (str or Prompt).
            session_id: Optional session ID for multi-turn.
            stream: If True, return async iterator of StreamChunk.
            include_tools: If set, only these tools are available for this run.
            exclude_tools: If set, these tools are excluded for this run.
            cancel_event: If set and triggered, cancels the run.
                Non-streaming: returns ``RunResult(output="(cancelled)")``.
                Streaming: yields a ``cancelled`` chunk.

        Returns:
            RunResult if stream=False, else AsyncIterator[StreamChunk].
        """
        # Auto-start MCP servers on first run (if enabled)
        if self._auto_start_mcp and not self._mcp_started:
            await self.start_mcp()

        # Auto-start LSP servers for configured languages
        if not self._lsp_started:
            await self.start_lsp()

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
                return self._stream_run(
                    prompt, session_id,
                    include_tools=include_tools, exclude_tools=exclude_tools,
                    cancel_event=cancel_event,
                )

            # Emit MODEL_REQUEST before calling the model
            if self._events:
                await self._events.dispatch_async(ModelEvent(
                    event_type=EventType.MODEL_REQUEST,
                    model=self._config.model.model or "",
                ))

            runner = self.get_runner()
            # Always use session to enable multi-turn by default
            store = self.get_session_store()
            result, sid = await runner.run_with_session(
                prompt, store, session_id,
                include_tools=include_tools, exclude_tools=exclude_tools,
                cancel_event=cancel_event,
            )

            run_result = RunResult(
                output=result.output,
                session_id=sid,
                usage=_usage_from_result(result),
                thinking=result.thinking,
                metadata=result.metadata,
            )

            # Emit MODEL_RESPONSE with usage
            if self._events:
                await self._events.dispatch_async(ModelEvent(
                    event_type=EventType.MODEL_RESPONSE,
                    model=self._config.model.model or "",
                    input_tokens=run_result.usage.input_tokens,
                    output_tokens=run_result.usage.output_tokens,
                ))

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
                await self._events.dispatch_async(ModelEvent(
                    event_type=EventType.MODEL_ERROR,
                    model=self._config.model.model or "",
                    error=str(e),
                ))
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
        cancel_event: Optional[asyncio.Event] = None,
        include_tools: list[str] | None = None,
        exclude_tools: list[str] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream agent response. Yields StreamChunk objects.

        SDK EventType events (STREAM_START/END, THINKING_START/END, TOOL_CALL,
        TOOL_RESULT, etc.) are dispatched automatically when an EventManager
        is configured.
        """
        # Auto-start MCP servers on first stream (if enabled)
        if self._auto_start_mcp and not self._mcp_started:
            await self.start_mcp()

        # Auto-start LSP servers for configured languages
        if not self._lsp_started:
            await self.start_lsp()

        runner = self.get_runner()
        store = self.get_session_store()

        in_thinking = False
        stream_started = False

        async for event, sid in runner.run_stream_with_session(
            prompt, store, session_id, cancel_event=cancel_event,
            include_tools=include_tools, exclude_tools=exclude_tools,
        ):
            chunk = _event_to_chunk(event, sid)

            # ── SDK event dispatch ──
            if self._events:
                # Emit STREAM_START on first non-session_start chunk
                if not stream_started and chunk.type != "session_start":
                    stream_started = True
                    await self._events.dispatch_async(SDKStreamEvent(
                        event_type=EventType.STREAM_START,
                        chunk_type="stream_start",
                    ))

                if chunk.type == "thinking":
                    if not in_thinking:
                        in_thinking = True
                        await self._events.dispatch_async(SDKThinkingEvent(
                            event_type=EventType.THINKING_START,
                            content="",
                            is_start=True,
                        ))
                    await self._events.dispatch_async(SDKThinkingEvent(
                        event_type=EventType.THINKING_CHUNK,
                        content=chunk.content,
                    ))
                else:
                    # End thinking block when a non-thinking chunk arrives
                    if in_thinking:
                        in_thinking = False
                        await self._events.dispatch_async(SDKThinkingEvent(
                            event_type=EventType.THINKING_END,
                            content="",
                            is_end=True,
                        ))

                    if chunk.type == "tool_call":
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
                    elif chunk.type == "compact":
                        await self._events.dispatch_async(SDKContextCompactEvent(
                            event_type=EventType.CONTEXT_COMPACT,
                            original_messages=chunk.original_messages,
                            compacted_messages=chunk.compacted_messages,
                            tokens_saved=chunk.estimated_tokens_saved,
                        ))
                    elif chunk.type == "done":
                        usage = chunk.usage
                        await self._events.dispatch_async(ModelEvent(
                            event_type=EventType.MODEL_RESPONSE,
                            model=self._config.model.model or "",
                            input_tokens=usage.input_tokens if usage else 0,
                            output_tokens=usage.output_tokens if usage else 0,
                        ))

                # Emit STREAM_END on done/cancelled/circuit_breaker
                if chunk.type in ("done", "cancelled", "circuit_breaker"):
                    if in_thinking:
                        in_thinking = False
                        await self._events.dispatch_async(SDKThinkingEvent(
                            event_type=EventType.THINKING_END,
                            content="",
                            is_end=True,
                        ))
                    await self._events.dispatch_async(SDKStreamEvent(
                        event_type=EventType.STREAM_END,
                        chunk_type="stream_end",
                    ))

            yield chunk

    # Alias for stream() — matches the name used in demos/docs
    run_stream = stream

    async def _stream_run(
        self, prompt, session_id: Optional[str] = None,
        include_tools: list[str] | None = None,
        exclude_tools: list[str] | None = None,
        cancel_event: Optional[asyncio.Event] = None,
    ):
        """Internal streaming run (called when run(stream=True)).

        Delegates to stream() which handles both chunk yielding and event dispatch.
        """
        async for chunk in self.stream(
            prompt, session_id=session_id,
            include_tools=include_tools, exclude_tools=exclude_tools,
            cancel_event=cancel_event,
        ):
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
        cfg = self._get_config()
        sm = SkillManager(config=cfg, workdir=effective_workdir)
        deps = CodyDeps(
            config=cfg,
            workdir=effective_workdir,
            skill_manager=sm,
            allowed_roots=[effective_workdir],
            strict_read_boundary=cfg.security.strict_read_boundary,
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
        store = self.get_session_store()
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
        store = self.get_session_store()
        sessions = store.list_sessions(limit=limit)
        return [
            SessionInfo(
                id=s.id,
                title=s.title,
                model=s.model,
                workdir=s.workdir,
                message_count=s.message_count if s.message_count is not None else len(s.messages),
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in sessions
        ]

    async def get_session(self, session_id: str) -> SessionDetail:
        """Get session with messages."""
        store = self.get_session_store()
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
        store = self.get_session_store()
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
        store = self.get_session_store()
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
        store = self.get_session_store()
        return store.get_message_count(session_id)

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Add a message to a session."""
        store = self.get_session_store()
        store.add_message(session_id, role, content)

    def update_title(self, session_id: str, title: str) -> None:
        """Update session title."""
        store = self.get_session_store()
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

    async def enable_skill(self, skill_name: str) -> None:
        """Enable a skill and persist the change to config."""
        from ..core.skill_manager import SkillManager
        from ..shared import resolve_config_path
        cfg = self._get_config()
        sm = SkillManager(config=cfg, workdir=self.workdir)
        skill = sm.get_skill(skill_name)
        if not skill:
            raise CodyNotFoundError(
                f"Skill not found: {skill_name}",
                code="SKILL_NOT_FOUND",
            )
        sm.enable_skill(skill_name)
        cfg.save(resolve_config_path())

    async def disable_skill(self, skill_name: str) -> None:
        """Disable a skill and persist the change to config."""
        from ..core.skill_manager import SkillManager
        from ..shared import resolve_config_path
        cfg = self._get_config()
        sm = SkillManager(config=cfg, workdir=self.workdir)
        skill = sm.get_skill(skill_name)
        if not skill:
            raise CodyNotFoundError(
                f"Skill not found: {skill_name}",
                code="SKILL_NOT_FOUND",
            )
        sm.disable_skill(skill_name)
        cfg.save(resolve_config_path())

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

    # ── MCP Methods ─────────────────────────────────────────────────────

    async def mcp_list_tools(self) -> list[dict]:
        """List all tools from connected MCP servers."""
        runner = self.get_runner()
        if not runner._mcp_client:
            return []
        return [
            {
                "name": f"{t.server_name}/{t.name}",
                "description": t.description,
                "input_schema": t.input_schema,
                "server": t.server_name,
            }
            for t in runner._mcp_client.list_tools()
        ]

    async def mcp_call(
        self,
        tool_name: str,
        arguments: dict | None = None,
    ) -> str:
        """Call an MCP tool by 'server_name/tool_name'."""
        runner = self.get_runner()
        if not runner._mcp_client:
            raise CodyConfigError("No MCP servers configured or started")
        result = await runner._mcp_client.call_tool(tool_name, arguments)
        return result

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

    # ── Interaction Methods ──────────────────────────────────────────────

    async def submit_interaction(
        self,
        request_id: str,
        action: Literal["approve", "reject", "revise", "answer"] = "answer",
        content: str = "",
    ) -> None:
        """Submit a human response to a pending interaction request.

        Args:
            request_id: The ID of the InteractionRequest to respond to.
            action: One of "approve", "reject", "revise", "answer".
            content: Response content (e.g., the user's answer or revision).
        """
        from ..core.interaction import InteractionResponse
        runner = self.get_runner()
        response = InteractionResponse(
            request_id=request_id, action=action, content=content,
        )
        await runner.submit_interaction(response)

    async def inject_user_input(self, message: str) -> None:
        """Send a proactive message to the running agent without waiting for it to ask.

        The message is queued and injected at the next node boundary
        (after current tool execution), so the LLM sees it on the next turn.

        Args:
            message: The text to inject into the conversation.
        """
        runner = self.get_runner()
        await runner.inject_user_input(message)

    # ── Memory Methods ────────────────────────────────────────────────────

    async def add_memory(
        self,
        category: str,
        content: str,
        *,
        source_task_id: str = "",
        source_task_title: str = "",
        confidence: float = 1.0,
        tags: list[str] | None = None,
    ) -> None:
        """Add a memory entry to the project memory store.

        Args:
            category: One of "conventions", "patterns", "issues", "decisions".
            content: The memory content.
            source_task_id: Optional task ID that produced this memory.
            source_task_title: Optional task title.
            confidence: Confidence score (0.0-1.0).
            tags: Optional tags for filtering.
        """
        from ..core.memory import MemoryEntry
        runner = self.get_runner()
        if not runner._memory_store:
            return
        entry = MemoryEntry(
            content=content,
            source_task_id=source_task_id,
            source_task_title=source_task_title,
            confidence=confidence,
            tags=tags or [],
        )
        await runner._memory_store.add_entries(category, [entry])

    async def get_memory(self) -> dict[str, list[dict]]:
        """Get all project memory entries grouped by category."""
        runner = self.get_runner()
        if not runner._memory_store:
            return {}
        all_entries = runner._memory_store.get_all_entries()
        return {
            cat: [
                {
                    "id": e.id,
                    "content": e.content,
                    "confidence": e.confidence,
                    "tags": e.tags,
                    "created_at": e.created_at,
                }
                for e in entries
            ]
            for cat, entries in all_entries.items()
        }

    async def clear_memory(self) -> None:
        """Clear all project memory."""
        runner = self.get_runner()
        if runner._memory_store:
            runner._memory_store.clear()

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

    def start_mcp(self) -> None:
        """Start MCP servers if configured."""
        _run_async(self._async.start_mcp())

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

    def enable_skill(self, skill_name: str):
        return _run_async(self._async.enable_skill(skill_name))

    def disable_skill(self, skill_name: str):
        return _run_async(self._async.disable_skill(skill_name))

    def get_message_count(self, session_id: str) -> int:
        return self._async.get_message_count(session_id)

    def add_message(self, session_id: str, role: str, content: str) -> None:
        self._async.add_message(session_id, role, content)

    def update_title(self, session_id: str, title: str) -> None:
        self._async.update_title(session_id, title)

    @staticmethod
    def messages_to_history(messages) -> list:
        return AsyncCodyClient.messages_to_history(messages)

    def mcp_list_tools(self) -> list[dict]:
        return _run_async(self._async.mcp_list_tools())

    def mcp_call(self, tool_name: str, arguments: dict | None = None) -> str:
        return _run_async(self._async.mcp_call(tool_name, arguments))

    def read_file(self, path: str) -> str:
        return _run_async(self._async.read_file(path))

    def write_file(self, path: str, content: str) -> str:
        return _run_async(self._async.write_file(path, content))

    def get_metrics(self) -> Optional[dict]:
        return self._async.get_metrics()

    def submit_interaction(self, request_id: str, action: str = "answer", content: str = "") -> None:
        _run_async(self._async.submit_interaction(request_id, action, content))

    def inject_user_input(self, message: str) -> None:
        _run_async(self._async.inject_user_input(message))

    def add_memory(self, category: str, content: str, **kwargs) -> None:
        _run_async(self._async.add_memory(category, content, **kwargs))

    def get_memory(self) -> dict:
        return _run_async(self._async.get_memory())

    def clear_memory(self) -> None:
        _run_async(self._async.clear_memory())
