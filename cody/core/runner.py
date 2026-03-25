"""Agent runner — the core execution engine of Cody.

AgentRunner is the central orchestrator. It:
  1. Creates a pydantic-ai Agent with the resolved model and system prompt
  2. Registers all tools via tools.register_tools() (declarative, not per-tool)
  3. Assembles CodyDeps (config, workdir, skill_manager, mcp, lsp, audit,
     permissions, file_history, todo_list) for dependency injection
  4. Provides run() / run_stream() / run_sync() for one-shot execution
  5. Provides run_with_session() / run_stream_with_session() for multi-turn
  6. Auto-compacts message history when approaching token limits

Dependency direction: server.py / cli.py / tui.py → runner.py → tools.py
Core never imports from shells.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, AsyncGenerator, Literal, Optional, Union

from pydantic_ai import Agent
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ImageUrl,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    UserPromptPart,
)
from pydantic_graph import End

from .audit import AuditLogger
from .retry import RetryConfig as _RetryDataclass, with_retry, with_retry_sync
from .config import Config
from .context import (
    CompactResult,
    compact_messages,
    compact_messages_llm,
    estimate_tokens,
    prune_tool_outputs,
)
from .deps import CodyDeps
from .errors import CircuitBreakerError, InteractionTimeoutError
from .file_history import FileHistory
from .interaction import InteractionRequest, InteractionResponse
from .log import log_elapsed
from .lsp_client import LSPClient
from .mcp_client import MCPClient
from .memory import ProjectMemoryStore
from .permissions import PermissionLevel, PermissionManager
from .prompt import Prompt, prompt_images, prompt_text
from .session import Message, SessionStore
from .skill_manager import SkillManager
from .sub_agent import SubAgentManager
from .user_input import UserInputQueue
from .model_resolver import resolve_model
from .project_instructions import load_project_instructions
from . import tools

logger = logging.getLogger(__name__)


# ── Result models ──────────────────────────────────────────────────────────


@dataclass
class ToolTrace:
    """Record of a single tool call and its result."""
    tool_name: str
    args: dict[str, Any]
    result: str
    tool_call_id: str = ""


@dataclass
class TaskMetadata:
    """Structured metadata extracted from a completed task."""
    summary: str = ""
    confidence: Optional[float] = None
    issues: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)


@dataclass
class CodyResult:
    """Rich result from the Cody engine.

    The core always provides all information. Upper layers (CLI, TUI, Server)
    decide what to display and how to render it.
    """
    output: str
    thinking: Optional[str] = None
    tool_traces: list[ToolTrace] = field(default_factory=list)
    metadata: Optional[TaskMetadata] = None
    _raw_result: Any = field(default=None, repr=False)

    def usage(self):
        """Proxy to pydantic-ai usage stats."""
        if self._raw_result:
            return self._raw_result.usage()
        return None

    def all_messages(self):
        """Proxy to pydantic-ai message history (for multi-turn)."""
        if self._raw_result:
            return self._raw_result.all_messages()
        return []

    @staticmethod
    def from_raw(raw_result) -> "CodyResult":
        """Extract CodyResult from a pydantic-ai AgentRunResult.

        Walks all_messages() to pull out ThinkingPart and ToolCall/ToolReturn pairs.
        """
        thinking_parts: list[str] = []
        tool_calls: dict[str, ToolTrace] = {}  # keyed by tool_call_id
        tool_traces: list[ToolTrace] = []

        for msg in raw_result.all_messages():
            if isinstance(msg, ModelResponse):
                for part in msg.parts:
                    if part.part_kind == "thinking" and part.content:
                        thinking_parts.append(part.content)
                    elif part.part_kind == "tool-call":
                        args = part.args if isinstance(part.args, dict) else {}
                        if isinstance(part.args, str):
                            try:
                                args = json.loads(part.args)
                            except (json.JSONDecodeError, TypeError):
                                args = {"raw": part.args}
                        trace = ToolTrace(
                            tool_name=part.tool_name,
                            args=args,
                            result="",
                            tool_call_id=part.tool_call_id,
                        )
                        tool_calls[part.tool_call_id] = trace
                        tool_traces.append(trace)

            elif isinstance(msg, ModelRequest):
                for part in msg.parts:  # type: ignore[assignment]
                    if part.part_kind == "tool-return":
                        if part.tool_call_id in tool_calls:
                            content = part.content
                            if not isinstance(content, str):
                                content = str(content)
                            tool_calls[part.tool_call_id].result = content

        output = raw_result.output
        metadata = _extract_metadata(output)

        return CodyResult(
            output=output,
            thinking="\n\n".join(thinking_parts) if thinking_parts else None,
            tool_traces=tool_traces,
            metadata=metadata,
            _raw_result=raw_result,
        )


# ── Stream event types ────────────────────────────────────────────────────


@dataclass
class ThinkingEvent:
    """Incremental thinking content from the model."""
    content: str
    event_type: Literal["thinking"] = "thinking"


@dataclass
class TextDeltaEvent:
    """Incremental text output from the model."""
    content: str
    event_type: Literal["text_delta"] = "text_delta"


@dataclass
class ToolCallEvent:
    """A tool call has been initiated."""
    tool_name: str
    args: dict[str, Any]
    tool_call_id: str
    event_type: Literal["tool_call"] = "tool_call"


@dataclass
class ToolResultEvent:
    """A tool call has returned a result."""
    tool_name: str
    tool_call_id: str
    result: str
    event_type: Literal["tool_result"] = "tool_result"


@dataclass
class PruneEvent:
    """Old tool outputs were selectively pruned before this run."""
    messages_pruned: int
    estimated_tokens_saved: int
    event_type: Literal["prune"] = "prune"


@dataclass
class CompactEvent:
    """Context was auto-compacted before this run."""
    original_messages: int
    compacted_messages: int
    estimated_tokens_saved: int
    used_llm: bool = False
    event_type: Literal["compact"] = "compact"


@dataclass
class DoneEvent:
    """Stream complete. Contains the full CodyResult."""
    result: CodyResult
    event_type: Literal["done"] = "done"


@dataclass
class CancelledEvent:
    """Run was cancelled by the caller."""
    event_type: Literal["cancelled"] = "cancelled"


@dataclass
class SessionStartEvent:
    """Emitted at the very beginning of run_stream_with_session with the session ID."""
    session_id: str
    event_type: Literal["session_start"] = "session_start"


@dataclass
class CircuitBreakerEvent:
    """Emitted when the circuit breaker trips."""
    reason: str  # "token_limit" | "cost_limit" | "loop_detected"
    tokens_used: int
    cost_usd: float
    event_type: Literal["circuit_breaker"] = "circuit_breaker"


@dataclass
class InteractionRequestEvent:
    """Emitted when the runner needs human input."""
    request: InteractionRequest
    event_type: Literal["interaction_request"] = "interaction_request"


@dataclass
class UserInputReceivedEvent:
    """User proactively sent a message (without AI asking). Will be visible next LLM turn."""
    content: str
    event_type: Literal["user_input_received"] = "user_input_received"


StreamEvent = Union[
    SessionStartEvent, PruneEvent, CompactEvent, ThinkingEvent, TextDeltaEvent,
    ToolCallEvent, ToolResultEvent, DoneEvent,
    CancelledEvent, CircuitBreakerEvent, InteractionRequestEvent,
    UserInputReceivedEvent,
]


# ── Metadata extraction helpers ──────────────────────────────────────────

_CONFIDENCE_RE = re.compile(r"<confidence>\s*([\d.]+)\s*</confidence>")


def _extract_metadata(output: str) -> TaskMetadata:
    """Extract structured metadata from model output text."""
    confidence: Optional[float] = None
    match = _CONFIDENCE_RE.search(output)
    if match:
        try:
            val = float(match.group(1))
            if 0.0 <= val <= 1.0:
                confidence = val
        except ValueError:
            pass

    # Build a one-line summary from the first non-empty line
    summary = ""
    for line in output.splitlines():
        stripped = line.strip()
        if stripped:
            summary = stripped[:200]
            break

    return TaskMetadata(summary=summary, confidence=confidence)


def _build_allowed_roots(workdir: Path, config_roots: list[str], extra_roots: list[Path]) -> list[Path]:
    """Merge config-level and runtime allowed roots into resolved absolute Paths.

    *workdir* is always the implicit allowed root, so it is excluded from the
    returned list (tools already check it separately).  Duplicates are dropped
    while preserving order.  *config_roots* must contain absolute paths only;
    a ValueError is raised otherwise.
    """
    workdir_resolved = workdir.resolve()
    seen: set[Path] = {workdir_resolved}
    result: list[Path] = []

    for s in config_roots:
        p = Path(s)
        if not p.is_absolute():
            raise ValueError(
                f"security.allowed_roots entries must be absolute paths, got: {s!r}"
            )
        rp = p.resolve()
        if rp not in seen:
            result.append(rp)
            seen.add(rp)

    for r in extra_roots:
        rp = r.resolve()
        if rp not in seen:
            result.append(rp)
            seen.add(rp)

    return result


class AgentRunner:
    """Run Cody Agent with full context"""

    def __init__(
        self,
        config: Config,
        workdir: Path,
        extra_roots: list[Path] | None = None,
        custom_tools: list | None = None,
        system_prompt: str | None = None,
        extra_system_prompt: str | None = None,
        before_tool_hooks: list | None = None,
        after_tool_hooks: list | None = None,
        audit_logger: object | None = None,
        file_history: object | None = None,
    ):
        self.workdir = workdir
        self.config = config
        self.allowed_roots: list[Path] = _build_allowed_roots(
            workdir, config.security.allowed_roots, extra_roots or []
        )
        self.skill_manager = SkillManager(self.config, workdir=self.workdir)

        # MCP client (created lazily on start)
        self._mcp_client: Optional[MCPClient] = None
        if self.config.mcp.servers:
            self._mcp_client = MCPClient(self.config.mcp)

        # Sub-agent manager
        self._sub_agent_manager = SubAgentManager(
            config=self.config,
            workdir=self.workdir,
        )

        # LSP client
        self._lsp_client = LSPClient(workdir=self.workdir)

        # Audit logger (injected or default SQLite)
        self._audit_logger = audit_logger if audit_logger is not None else AuditLogger()

        # Permission manager
        self._permission_manager = PermissionManager(
            overrides=self.config.permissions.overrides,
            default_level=PermissionLevel(self.config.permissions.default_level),
        )

        # File history (injected or default in-memory)
        self._file_history = file_history if file_history is not None else FileHistory(workdir=self.workdir)

        # Shared todo list for AI task tracking
        self._todo_list: list = []

        # Circuit breaker state (reset per run)
        self._cb_total_tokens: int = 0
        self._cb_estimated_cost: float = 0.0
        self._cb_step_count: int = 0
        self._cb_recent_results: list[str] = []

        # Pending interaction requests (id → Future).
        # Futures are created by consumers (CLI/TUI/Web) when they emit
        # InteractionRequestEvent; submit_interaction() resolves them.
        self._pending_interactions: dict[str, asyncio.Future] = {}

        # User input queue: users can proactively send messages without AI asking.
        self._user_input_queue = UserInputQueue()

        # Custom tools provided by the SDK user
        self._custom_tools: list = custom_tools or []

        # Custom system prompt overrides
        self._system_prompt_override: str | None = system_prompt
        self._extra_system_prompt: str | None = extra_system_prompt

        # Step hooks (before/after tool execution)
        self._before_tool_hooks: list = before_tool_hooks or []
        self._after_tool_hooks: list = after_tool_hooks or []

        # Project memory
        self._memory_store: Optional[ProjectMemoryStore] = None
        try:
            self._memory_store = ProjectMemoryStore.from_workdir(self.workdir)
        except Exception:
            logger.debug("ProjectMemoryStore init failed, continuing without memory", exc_info=True)

        # Create agent
        self.agent = self._create_agent()

    def _resolve_model(self):
        """Resolve model to a Pydantic AI model instance.

        Delegates to model_resolver.resolve_model() which is shared with
        SubAgentManager to keep both in sync.
        """
        return resolve_model(self.config)

    def _create_agent(
        self,
        *,
        include_tools: list[str] | None = None,
        exclude_tools: list[str] | None = None,
    ) -> Agent:
        """Create Pydantic AI Agent with tools.

        Tools are registered declaratively via tools.register_tools() —
        see tools.py CORE_TOOLS / MCP_TOOLS for the full list.

        System prompt order:
          1. Base persona (or user-provided system_prompt override)
          2. CODY.md project instructions (global ~/.cody/CODY.md + project CODY.md)
          3. Project memory (cross-session learnings)
          4. Available skills XML (Agent Skills standard)
          5. extra_system_prompt (user-provided, appended last)

        Args:
            include_tools: If set, only register tools with these names.
            exclude_tools: If set, skip tools with these names.
        """
        # 1. Base persona (from core/prompts.py), or custom override
        if self._system_prompt_override is not None:
            system_parts = [self._system_prompt_override]
        else:
            from .prompts import build_system_prompt
            system_parts = [build_system_prompt()]

        # 2. CODY.md project instructions (global + project, merged)
        project_instructions = load_project_instructions(self.workdir)
        if project_instructions:
            system_parts.append(
                "## Project Instructions (from CODY.md)\n\n" + project_instructions
            )

        # 3. Project memory (cross-session learnings)
        if self._memory_store:
            memory_prompt = self._memory_store.get_memory_for_prompt()
            if memory_prompt:
                system_parts.append(memory_prompt)

        # 4. Available skills
        skills_xml = self.skill_manager.to_prompt_xml()
        if skills_xml:
            system_parts.append(skills_xml)

        # 5. Extra system prompt (user-provided, appended last)
        if self._extra_system_prompt:
            system_parts.append(self._extra_system_prompt)

        agent = Agent(
            self._resolve_model(),
            deps_type=CodyDeps,
            system_prompt="\n\n".join(system_parts),
        )

        tools.register_tools(
            agent,
            include_mcp=bool(self._mcp_client),
            custom_tools=self._custom_tools or None,
            include_tools=include_tools,
            exclude_tools=exclude_tools,
        )

        # Dynamic system prompt: MCP tools (evaluated at each run,
        # so it always reflects currently connected servers & tools)
        if self._mcp_client:
            mcp_client = self._mcp_client

            @agent.system_prompt
            def mcp_tools_prompt() -> str:
                mcp_tools = mcp_client.list_tools()
                if not mcp_tools:
                    return ""
                lines = [
                    "## MCP Tools (Model Context Protocol)\n",
                    "You have access to external tools via MCP servers. "
                    "Use mcp_call(tool_name, arguments) to invoke them. "
                    "The tool_name must be in 'server/tool' format.\n",
                    "Available MCP tools:",
                ]
                for t in mcp_tools:
                    lines.append(f"- **{t.server_name}/{t.name}**: {t.description}")
                    if t.input_schema and t.input_schema.get("properties"):
                        params = ", ".join(
                            f"`{k}` ({v.get('type', '?')})"
                            for k, v in t.input_schema["properties"].items()
                        )
                        lines.append(f"  Parameters: {params}")
                return "\n".join(lines)

        return agent  # type: ignore[return-value]

    def _get_agent(
        self,
        include_tools: list[str] | None = None,
        exclude_tools: list[str] | None = None,
    ) -> Agent:
        """Return the agent to use for a run.

        If *include_tools* or *exclude_tools* is specified, a new agent is
        created with filtered tools (one-off, not cached).  Otherwise,
        the default agent (``self.agent``) is returned.
        """
        if include_tools is not None or exclude_tools is not None:
            return self._create_agent(
                include_tools=include_tools,
                exclude_tools=exclude_tools,
            )
        return self.agent

    def _create_deps(self, interaction_handler=None) -> CodyDeps:
        """Create dependencies.

        *interaction_handler*: async callable ``(InteractionRequest) -> InteractionResponse``.
        Defaults to auto-approve when ``None``.
        """
        return CodyDeps(
            config=self.config,
            workdir=self.workdir,
            skill_manager=self.skill_manager,
            allowed_roots=self.allowed_roots,
            strict_read_boundary=self.config.security.strict_read_boundary,
            mcp_client=self._mcp_client,
            sub_agent_manager=self._sub_agent_manager,
            lsp_client=self._lsp_client,
            audit_logger=self._audit_logger,
            permission_manager=self._permission_manager,
            file_history=self._file_history,
            todo_list=self._todo_list,
            memory_store=self._memory_store,
            interaction_handler=interaction_handler or self._auto_approve_handler,
            before_tool_hooks=self._before_tool_hooks,
            after_tool_hooks=self._after_tool_hooks,
        )

    # ── MCP lifecycle ────────────────────────────────────────────────────────

    async def start_mcp(self) -> None:
        """Start MCP servers if configured.

        MCP tool descriptions are injected via dynamic system prompt,
        so they automatically reflect the tools discovered at start time.
        """
        if self._mcp_client:
            await self._mcp_client.start_all()

    async def stop_mcp(self) -> None:
        """Stop MCP servers."""
        if self._mcp_client:
            await self._mcp_client.stop_all()

    # ── LSP lifecycle ─────────────────────────────────────────────────────────

    async def start_lsp(self, language: str) -> bool:
        """Start an LSP server for the given language."""
        return await self._lsp_client.start(language)

    async def stop_lsp(self) -> None:
        """Stop all LSP servers."""
        await self._lsp_client.stop_all()

    # ── Session helpers ──────────────────────────────────────────────────────

    @staticmethod
    def messages_to_history(messages: list[Message]) -> list[ModelMessage]:
        """Convert stored session messages to pydantic-ai ModelMessage format."""
        history: list[ModelMessage] = []
        for msg in messages:
            if msg.role == "user":
                if msg.images:
                    # Reconstruct multimodal prompt for history using data URIs
                    parts: list = [msg.content]
                    for img in msg.images:
                        data_uri = f"data:{img.media_type};base64,{img.data}"
                        parts.append(ImageUrl(url=data_uri))
                    history.append(ModelRequest(parts=[UserPromptPart(content=parts)]))
                else:
                    history.append(ModelRequest(parts=[UserPromptPart(content=msg.content)]))
            elif msg.role == "assistant":
                history.append(ModelResponse(parts=[TextPart(content=msg.content)]))
        return history

    def prepare_session(
        self,
        store: SessionStore,
        session_id: Optional[str] = None,
    ) -> tuple[str, Optional[list[ModelMessage]]]:
        """Load existing session or create a new one.

        If a compaction checkpoint exists, builds history from the saved summary
        plus only the messages added after the checkpoint, avoiding redundant
        re-compaction of already-summarized messages.

        Returns (session_id, history_or_none).
        """
        if session_id:
            session = store.get_session(session_id)
            if not session:
                raise ValueError(f"Session not found: {session_id}")

            # Use compaction checkpoint if available
            if session.compacted_summary and session.compacted_up_to is not None:
                recent_msgs = store.get_messages_after(
                    session_id, session.compacted_up_to
                )
                compacted_history: list[ModelMessage] = [
                    ModelRequest(parts=[UserPromptPart(
                        content=f"[Context]\n{session.compacted_summary}"
                    )])
                ]
                compacted_history.extend(self.messages_to_history(recent_msgs))
                return session.id, compacted_history

            history: Optional[list[ModelMessage]] = (
                self.messages_to_history(session.messages) if session.messages else None
            )
            return session.id, history

        session = store.create_session(
            model=self.config.model,
            workdir=str(self.workdir),
        )
        return session.id, None

    # ── Context compaction ────────────────────────────────────────────────────

    def _history_to_dicts(
        self,
        history: list[ModelMessage],
    ) -> list[dict]:
        """Convert ModelMessage list → dict list for compaction/pruning."""
        msgs: list[dict] = []
        for msg in history:
            if isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if hasattr(part, 'content'):
                        msgs.append({"role": "user", "content": part.content})
            elif isinstance(msg, ModelResponse):
                for part in msg.parts:  # type: ignore[assignment]
                    if hasattr(part, 'content'):
                        msgs.append({"role": "assistant", "content": part.content})
        return msgs

    @staticmethod
    def _dicts_to_history(msgs: list[dict]) -> list[ModelMessage]:
        """Convert dict list back to ModelMessage format."""
        new_history: list[ModelMessage] = []
        for m in msgs:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "system":
                new_history.append(
                    ModelRequest(parts=[UserPromptPart(content=f"[Context]\n{content}")])
                )
            elif role == "user":
                new_history.append(ModelRequest(parts=[UserPromptPart(content=content)]))
            elif role == "assistant":
                new_history.append(ModelResponse(parts=[TextPart(content=content)]))
        return new_history

    async def _compact_history_if_needed(
        self,
        history: Optional[list[ModelMessage]],
        max_tokens: int = 100_000,
    ) -> tuple[Optional[list[ModelMessage]], Optional[CompactResult]]:
        """Auto-compact message history when approaching token limits.

        Uses a two-phase strategy inspired by OpenCode:

        1. **Prune** — selectively replace old, large tool outputs with
           lightweight markers.  This preserves conversation structure and is
           very cheap (no LLM call).
        2. **Compact** — if pruning alone didn't free enough tokens, fall back
           to full compaction (truncation or LLM summarization).

        The effective token threshold is determined by
        ``CompactionConfig.effective_max_tokens()`` which honours
        ``trigger_ratio`` and ``context_window_tokens`` when set.

        Returns (history, compact_result_or_none).
        """
        if not history:
            return history, None

        msgs = self._history_to_dicts(history)
        cc = self.config.compaction
        eff_max = cc.effective_max_tokens()

        # ── Phase 1: Selective pruning ───────────────────────────────────
        if cc.enable_pruning:
            pruned, prune_result = prune_tool_outputs(
                msgs,
                max_tokens=eff_max,
                protect_recent_tokens=cc.prune_protect_tokens,
                min_saving_tokens=cc.prune_min_saving_tokens,
                min_content_tokens=cc.prune_min_content_tokens,
            )
            if prune_result is not None:
                logger.info(
                    "Pruned %d messages, ~%d tokens saved",
                    prune_result.messages_pruned,
                    prune_result.estimated_tokens_saved,
                )
                msgs = pruned
                # Re-check: is pruning sufficient?
                remaining = sum(
                    estimate_tokens(m.get("content", "")) for m in msgs
                )
                if remaining <= eff_max:
                    # Pruning was enough — convert back and return
                    return (
                        self._dicts_to_history(msgs),
                        CompactResult(
                            summary="",
                            original_messages=len(history),
                            compacted_messages=len(msgs),
                            estimated_tokens_saved=prune_result.estimated_tokens_saved,
                        ),
                    )

        # ── Phase 2: Full compaction ─────────────────────────────────────

        # Extract existing summary for incremental compaction
        existing_summary = ""
        if (
            msgs
            and msgs[0].get("role") == "user"
            and "Previous conversation summary" in msgs[0].get("content", "")
        ):
            existing_summary = msgs[0]["content"]
            # Remove the [Context] prefix if present
            if existing_summary.startswith("[Context]\n"):
                existing_summary = existing_summary[len("[Context]\n"):]
            msgs = msgs[1:]

        if self.config.compaction.use_llm:
            try:
                compacted, result = await compact_messages_llm(
                    msgs,
                    config=self.config,
                    existing_summary=existing_summary,
                    max_tokens=eff_max,
                    keep_recent=cc.keep_recent,
                    keep_recent_tokens=cc.keep_recent_tokens,
                    max_summary_tokens=cc.max_summary_tokens,
                )
            except Exception:
                logger.warning(
                    "LLM compaction failed, falling back to truncation",
                    exc_info=True,
                )
                compacted, result = compact_messages(
                    msgs,
                    max_tokens=eff_max,
                    keep_recent_tokens=cc.keep_recent_tokens,
                )
        else:
            compacted, result = compact_messages(
                msgs,
                max_tokens=eff_max,
                keep_recent_tokens=cc.keep_recent_tokens,
            )

        if result is None:
            return history, None  # no compaction needed

        logger.info(
            "Context compacted: %d → %d messages, ~%d tokens saved (llm=%s)",
            result.original_messages,
            result.compacted_messages,
            result.estimated_tokens_saved,
            result.used_llm,
        )

        return self._dicts_to_history(compacted), result

    def _compact_history_sync(
        self,
        history: Optional[list[ModelMessage]],
        max_tokens: int = 100_000,
    ) -> tuple[Optional[list[ModelMessage]], Optional[CompactResult]]:
        """Synchronous compaction — prune first, then truncation (no LLM)."""
        if not history:
            return history, None

        msgs = self._history_to_dicts(history)
        cc = self.config.compaction
        eff_max = cc.effective_max_tokens()

        # Phase 1: Selective pruning
        if cc.enable_pruning:
            pruned, prune_result = prune_tool_outputs(
                msgs,
                max_tokens=eff_max,
                protect_recent_tokens=cc.prune_protect_tokens,
                min_saving_tokens=cc.prune_min_saving_tokens,
                min_content_tokens=cc.prune_min_content_tokens,
            )
            if prune_result is not None:
                msgs = pruned
                remaining = sum(
                    estimate_tokens(m.get("content", "")) for m in msgs
                )
                if remaining <= eff_max:
                    return (
                        self._dicts_to_history(msgs),
                        CompactResult(
                            summary="",
                            original_messages=len(history),
                            compacted_messages=len(msgs),
                            estimated_tokens_saved=prune_result.estimated_tokens_saved,
                        ),
                    )

        # Phase 2: Truncation
        compacted, result = compact_messages(
            msgs,
            max_tokens=eff_max,
            keep_recent_tokens=cc.keep_recent_tokens,
        )
        if result is None:
            return history, None

        return self._dicts_to_history(compacted), result

    # ── Model settings ────────────────────────────────────────────────────────

    def _build_model_settings(self) -> Optional[dict[str, Any]]:
        """Build model_settings dict for pydantic-ai, including thinking support.

        Returns None if no special settings are needed.
        """
        if not self.config.enable_thinking:
            return None

        extra_body: dict[str, Any] = {"enable_thinking": True}
        if self.config.thinking_budget is not None:
            extra_body["thinking_budget"] = self.config.thinking_budget

        return {"extra_body": extra_body}

    def _retry_config(self) -> _RetryDataclass:
        """Build retry dataclass from pydantic config."""
        rc = self.config.retry
        return _RetryDataclass(
            max_retries=rc.max_retries,
            base_delay=rc.base_delay,
            max_delay=rc.max_delay,
            enabled=rc.enabled,
        )

    # ── Circuit breaker ────────────────────────────────────────────────────

    def _reset_circuit_breaker(self) -> None:
        """Reset circuit breaker counters for a new run."""
        self._cb_total_tokens = 0
        self._cb_estimated_cost = 0.0
        self._cb_step_count = 0
        self._cb_recent_results = []

    def _update_circuit_breaker(self, result_text: str, usage: Any) -> None:
        """Update circuit breaker state after a tool call or model response."""
        if usage:
            tokens = getattr(usage, "total_tokens", 0) or 0
            self._cb_total_tokens = tokens
            price = self.config.circuit_breaker.model_prices.get(
                self.config.model,
                self.config.circuit_breaker.model_prices.get("default", 0.000003),
            )
            self._cb_estimated_cost = self._cb_total_tokens * price

        if result_text:
            self._cb_step_count += 1
            self._cb_recent_results.append(result_text)
            max_keep = self.config.circuit_breaker.loop_detect_turns + 1
            if len(self._cb_recent_results) > max_keep:
                self._cb_recent_results = self._cb_recent_results[-max_keep:]

    def _check_circuit_breaker(self) -> None:
        """Check circuit breaker conditions and raise if tripped."""
        if not self.config.circuit_breaker.enabled:
            return
        cb = self.config.circuit_breaker
        if self._cb_total_tokens > cb.max_tokens:
            raise CircuitBreakerError("token_limit", self._cb_total_tokens, self._cb_estimated_cost)
        if self._cb_estimated_cost > cb.max_cost_usd:
            raise CircuitBreakerError("cost_limit", self._cb_total_tokens, self._cb_estimated_cost)
        if cb.max_steps > 0 and self._cb_step_count > cb.max_steps:
            raise CircuitBreakerError("step_limit", self._cb_total_tokens, self._cb_estimated_cost)
        if self._is_loop_detected():
            raise CircuitBreakerError("loop_detected", self._cb_total_tokens, self._cb_estimated_cost)

    def _is_loop_detected(self) -> bool:
        """Check if recent tool results indicate a loop."""
        n = self.config.circuit_breaker.loop_detect_turns
        if len(self._cb_recent_results) < n:
            return False
        recent = self._cb_recent_results[-n:]
        threshold = self.config.circuit_breaker.loop_similarity_threshold
        # All recent results must be similar to each other
        first = recent[0]
        return all(
            SequenceMatcher(None, first, r).ratio() >= threshold
            for r in recent[1:]
        )

    # ── Interaction (human-in-the-loop) ──────────────────────────────────

    async def submit_interaction(self, response: InteractionResponse) -> None:
        """Submit a human response to a pending interaction request."""
        future = self._pending_interactions.pop(response.request_id, None)
        if future and not future.done():
            future.set_result(response)

    async def inject_user_input(self, message: str) -> None:
        """Send a proactive message to the running agent.

        The message is queued and injected at the next node boundary
        (after tool execution completes), so the LLM sees it on the
        next turn alongside tool results.
        """
        await self._user_input_queue.put(message)

    @staticmethod
    async def _auto_approve_handler(request: InteractionRequest) -> InteractionResponse:
        """Default handler: auto-approve all interaction requests."""
        return InteractionResponse(request_id=request.id, action="approve")

    def _build_stream_interaction_handler(self, interaction_q: asyncio.Queue):
        """Build an interaction handler for streaming mode.

        If interaction is disabled, returns auto-approve.
        If enabled, returns a handler that:
          1. Pushes InteractionRequestEvent to the interaction queue
          2. Creates a Future in _pending_interactions
          3. Awaits the Future with configured timeout
          4. Raises InteractionTimeoutError on timeout

        The interaction_q is a side channel: interaction events are pushed
        here during tool execution (inside CallToolsNode) and drained by
        the run_stream generator between stream events.
        """
        if not self.config.interaction.enabled:
            return self._auto_approve_handler

        timeout = self.config.interaction.timeout

        async def _handler(request: InteractionRequest) -> InteractionResponse:
            future: asyncio.Future[InteractionResponse] = asyncio.get_running_loop().create_future()
            self._pending_interactions[request.id] = future
            await interaction_q.put(InteractionRequestEvent(request=request))
            try:
                if timeout > 0:
                    return await asyncio.wait_for(future, timeout=timeout)
                return await future
            except asyncio.TimeoutError:
                self._pending_interactions.pop(request.id, None)
                raise InteractionTimeoutError(request.id, timeout)

        return _handler

    # ── Prompt conversion ───────────────────────────────────────────────────

    @staticmethod
    def _to_pydantic_prompt(prompt: Prompt):
        """Convert a Prompt to pydantic-ai's user_prompt format.

        str → str (unchanged, backward compatible)
        MultimodalPrompt → list[str | ImageUrl] using data URIs
        """
        if isinstance(prompt, str):
            return prompt
        parts: list = []
        if prompt.text:
            parts.append(prompt.text)
        for img in prompt.images:
            data_uri = f"data:{img.media_type};base64,{img.data}"
            parts.append(ImageUrl(url=data_uri))
        return parts if parts else prompt.text

    # ── Core run methods ─────────────────────────────────────────────────────

    @log_elapsed("AgentRunner.run", level=logging.INFO)
    async def run(
        self,
        prompt: Prompt,
        message_history: Optional[list[ModelMessage]] = None,
        include_tools: list[str] | None = None,
        exclude_tools: list[str] | None = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> CodyResult:
        """Run agent with prompt, optionally continuing from history.

        Args:
            prompt: Task description.
            message_history: Prior conversation messages.
            include_tools: If set, only these tools are available for this run.
            exclude_tools: If set, these tools are excluded for this run.
            cancel_event: If set and triggered, the run is cancelled and
                a ``CodyResult`` with output ``"(cancelled)"`` is returned.
        """
        self._reset_circuit_breaker()
        deps = self._create_deps()
        message_history, _compact = await self._compact_history_if_needed(message_history)
        pydantic_prompt = self._to_pydantic_prompt(prompt)
        agent = self._get_agent(include_tools=include_tools, exclude_tools=exclude_tools)

        run_coro = with_retry(
            agent.run,  # type: ignore[call-overload]
            pydantic_prompt, deps=deps, message_history=message_history,
            model_settings=self._build_model_settings(),
            retry_config=self._retry_config(),
        )

        if cancel_event is not None:
            run_task = asyncio.ensure_future(run_coro)
            cancel_task = asyncio.ensure_future(cancel_event.wait())
            done, pending = await asyncio.wait(
                {run_task, cancel_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
            if cancel_task in done:
                return CodyResult(output="(cancelled)")
            result = run_task.result()
        else:
            result = await run_coro

        cody_result = CodyResult.from_raw(result)
        self._update_circuit_breaker("", result.usage() if hasattr(result, 'usage') else None)
        self._check_circuit_breaker()
        return cody_result

    @log_elapsed("AgentRunner.run_stream", level=logging.INFO)
    async def run_stream(
        self,
        prompt: Prompt,
        message_history: Optional[list[ModelMessage]] = None,
        cancel_event: Optional[asyncio.Event] = None,
        include_tools: list[str] | None = None,
        exclude_tools: list[str] | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Run agent with streaming, yielding structured StreamEvent objects.

        Uses pydantic-ai's ``agent.iter()`` API for node-level control,
        which enables proactive user input injection between nodes.

        Args:
            prompt: Task description.
            message_history: Prior conversation messages.
            cancel_event: Set to cancel the run.
            include_tools: If set, only these tools are available for this run.
            exclude_tools: If set, these tools are excluded for this run.

        Events:
          - CompactEvent: context was auto-compacted (first event if applicable)
          - ThinkingEvent: incremental thinking content
          - TextDeltaEvent: incremental text output
          - ToolCallEvent: tool call initiated
          - ToolResultEvent: tool call result
          - DoneEvent: stream complete with full CodyResult
          - CancelledEvent: run was cancelled via cancel_event
          - CircuitBreakerEvent: run terminated by circuit breaker
          - InteractionRequestEvent: human input needed
          - UserInputReceivedEvent: user proactively sent a message

        Raises:
          InteractionTimeoutError: if an interaction request times out
        """
        self._reset_circuit_breaker()

        # Side channel for interaction events emitted from within tool execution.
        interaction_q: asyncio.Queue = asyncio.Queue()

        # Build interaction handler for this stream.
        interaction_handler = self._build_stream_interaction_handler(interaction_q)
        deps = self._create_deps(interaction_handler=interaction_handler)

        message_history, compact_result = await self._compact_history_if_needed(
            message_history,
        )

        if compact_result is not None:
            yield CompactEvent(
                original_messages=compact_result.original_messages,
                compacted_messages=compact_result.compacted_messages,
                estimated_tokens_saved=compact_result.estimated_tokens_saved,
                used_llm=compact_result.used_llm,
            )

        pydantic_prompt = self._to_pydantic_prompt(prompt)

        def _drain_interaction_q():
            """Drain interaction events that were pushed during tool execution."""
            events = []
            while True:
                try:
                    events.append(interaction_q.get_nowait())
                except asyncio.QueueEmpty:
                    break
            return events

        # Drain any stale user input from a previous run.
        self._user_input_queue.drain_all()

        agent = self._get_agent(include_tools=include_tools, exclude_tools=exclude_tools)

        try:
            async with agent.iter(  # type: ignore[call-overload]
                pydantic_prompt, deps=deps, message_history=message_history,
                model_settings=self._build_model_settings(),
            ) as agent_run:
                async for node in agent_run:
                    if cancel_event and cancel_event.is_set():
                        yield CancelledEvent()
                        return

                    # UserPromptNode is handled automatically by iter().
                    # We only need to stream ModelRequestNode and CallToolsNode.

                    if agent.is_model_request_node(node):
                        # Stream LLM response: thinking + text deltas
                        async with node.stream(agent_run.ctx) as stream:  # type: ignore[var-annotated]
                            async for event in stream:
                                if isinstance(event, PartStartEvent):
                                    part = event.part
                                    if part.part_kind == "thinking" and getattr(part, "content", ""):  # type: ignore[arg-type]
                                        yield ThinkingEvent(content=part.content)
                                    elif part.part_kind == "text" and getattr(part, "content", ""):  # type: ignore[arg-type]
                                        yield TextDeltaEvent(content=part.content)
                                elif isinstance(event, PartDeltaEvent):
                                    delta = event.delta
                                    if delta.part_delta_kind == "thinking":
                                        content = getattr(delta, "content_delta", None)
                                        if content:
                                            yield ThinkingEvent(content=content)
                                    elif delta.part_delta_kind == "text":
                                        content = getattr(delta, "content_delta", None)
                                        if content:
                                            yield TextDeltaEvent(content=content)

                    elif agent.is_call_tools_node(node):
                        # Inject proactive user input alongside tool results.
                        # node.user_prompt is appended after tool return parts
                        # as a UserPromptPart, so the LLM sees it on the next turn.
                        user_messages = self._user_input_queue.drain_all()
                        if user_messages:
                            combined = "\n".join(user_messages)
                            node.user_prompt = combined  # type: ignore[union-attr]
                            yield UserInputReceivedEvent(content=combined)

                        # Stream tool calls and results, merging interaction
                        # events that may arrive while tools are executing.
                        # We use a merged queue so that interaction_request events
                        # are yielded to the caller even when a tool (e.g. question)
                        # is blocked awaiting a response via its Future.
                        _merged_q: asyncio.Queue = asyncio.Queue()
                        _TOOL_STREAM_DONE = object()

                        async def _consume_tool_stream():
                            async with node.stream(agent_run.ctx) as tool_stream:
                                async for ev in tool_stream:
                                    await _merged_q.put(("tool", ev))
                            await _merged_q.put(("done", _TOOL_STREAM_DONE))

                        async def _forward_interactions():
                            while True:
                                ia_event = await interaction_q.get()
                                await _merged_q.put(("interaction", ia_event))

                        _tool_task = asyncio.create_task(_consume_tool_stream())
                        _ia_task = asyncio.create_task(_forward_interactions())

                        try:
                            while True:
                                kind, item = await _merged_q.get()
                                if kind == "done":
                                    break
                                if kind == "interaction":
                                    yield item
                                    continue
                                # kind == "tool"
                                event = item
                                if isinstance(event, FunctionToolCallEvent):
                                    part = event.part
                                    args = part.args if isinstance(part.args, dict) else {}
                                    if isinstance(part.args, str):
                                        try:
                                            args = json.loads(part.args)
                                        except (json.JSONDecodeError, TypeError):
                                            args = {"raw": part.args}
                                    yield ToolCallEvent(
                                        tool_name=part.tool_name,
                                        args=args,
                                        tool_call_id=part.tool_call_id,
                                    )
                                elif isinstance(event, FunctionToolResultEvent):
                                    result_part = event.result
                                    if result_part.part_kind == "tool-return":
                                        content = result_part.content
                                        if not isinstance(content, str):
                                            content = str(content)
                                        yield ToolResultEvent(
                                            tool_name=result_part.tool_name,
                                            tool_call_id=result_part.tool_call_id,
                                            result=content,
                                        )
                                        self._update_circuit_breaker(content, None)
                        finally:
                            _ia_task.cancel()
                            try:
                                await _ia_task
                            except asyncio.CancelledError:
                                pass
                            if not _tool_task.done():
                                await _tool_task

                        # Drain any remaining interaction events after tool execution
                        for interaction_event in _drain_interaction_q():
                            yield interaction_event

                        # Check circuit breaker after each tool execution round
                        self._check_circuit_breaker()

                    elif isinstance(node, End):
                        # Final result
                        assert agent_run.result is not None
                        self._update_circuit_breaker(
                            "", agent_run.result.usage() if hasattr(agent_run.result, 'usage') else None,
                        )
                        self._check_circuit_breaker()
                        cody_result = CodyResult.from_raw(agent_run.result)
                        yield DoneEvent(result=cody_result)

        except CircuitBreakerError as e:
            yield CircuitBreakerEvent(
                reason=e.reason,
                tokens_used=e.tokens_used,
                cost_usd=e.cost_usd,
            )

    @log_elapsed("AgentRunner.run_sync", level=logging.INFO)
    def run_sync(
        self,
        prompt: Prompt,
        message_history: Optional[list[ModelMessage]] = None,
    ) -> CodyResult:
        """Run agent synchronously.

        Note: LLM compaction is not available in sync mode. Falls back to
        truncation-based compaction regardless of config.compaction.use_llm.
        """
        self._reset_circuit_breaker()
        # run_sync always auto-approves — interaction requires async
        if self.config.interaction.enabled:
            logger.warning(
                "interaction.enabled is ignored in run_sync (requires async); "
                "all interaction requests will be auto-approved"
            )
        deps = self._create_deps()  # auto-approve handler by default
        if self.config.compaction.use_llm:
            logger.debug(
                "LLM compaction unavailable in run_sync, using truncation"
            )
        message_history, _compact = self._compact_history_sync(message_history)
        pydantic_prompt = self._to_pydantic_prompt(prompt)
        result = with_retry_sync(
            self.agent.run_sync,  # type: ignore[call-overload]
            pydantic_prompt, deps=deps, message_history=message_history,
            model_settings=self._build_model_settings(),
            retry_config=self._retry_config(),
        )
        cody_result = CodyResult.from_raw(result)
        self._update_circuit_breaker("", result.usage() if hasattr(result, 'usage') else None)
        self._check_circuit_breaker()
        return cody_result

    # ── Session-aware run methods ────────────────────────────────────────────

    def _save_compaction_checkpoint(
        self,
        store: SessionStore,
        session_id: str,
        compact_result: CompactResult,
    ) -> None:
        """Persist compaction summary as a checkpoint in the session store."""
        last_msg_id = store.get_last_message_id(session_id)
        if last_msg_id is not None:
            store.save_compaction(
                session_id, compact_result.summary, last_msg_id,
            )
            logger.info(
                "Compaction checkpoint saved for session %s (up_to=%d)",
                session_id, last_msg_id,
            )

    @log_elapsed("AgentRunner.run_with_session", level=logging.INFO)
    async def run_with_session(
        self,
        prompt: Prompt,
        store: SessionStore,
        session_id: Optional[str] = None,
        include_tools: list[str] | None = None,
        exclude_tools: list[str] | None = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> tuple[CodyResult, str]:
        """Run agent with automatic session persistence.

        Returns (CodyResult, session_id). Creates a new session if session_id is None.
        Compaction checkpoints are persisted so subsequent turns skip
        re-compacting already-summarized messages.
        """
        sid, history = self.prepare_session(store, session_id)

        # Pre-compact and save checkpoint before running agent
        history, compact_result = await self._compact_history_if_needed(history)
        if compact_result is not None:
            self._save_compaction_checkpoint(store, sid, compact_result)

        result = await self.run(
            prompt, message_history=history,
            include_tools=include_tools, exclude_tools=exclude_tools,
            cancel_event=cancel_event,
        )
        store.add_message(sid, "user", prompt_text(prompt), images=prompt_images(prompt) or None)
        store.add_message(sid, "assistant", result.output)
        return result, sid

    @log_elapsed("AgentRunner.run_stream_with_session", level=logging.INFO)
    async def run_stream_with_session(
        self,
        prompt: Prompt,
        store: SessionStore,
        session_id: Optional[str] = None,
        cancel_event: Optional[asyncio.Event] = None,
        include_tools: list[str] | None = None,
        exclude_tools: list[str] | None = None,
    ) -> AsyncGenerator[tuple[StreamEvent, str], None]:
        """Stream agent with automatic session persistence.

        Yields (StreamEvent, session_id) tuples.
        Saves user+assistant messages; assistant message saved when DoneEvent arrives.
        Compaction checkpoints are persisted so subsequent turns skip
        re-compacting already-summarized messages.
        """
        sid, history = self.prepare_session(store, session_id)

        # Yield session ID immediately so callers always receive it,
        # even if the AI call fails later.
        yield SessionStartEvent(session_id=sid), sid

        # Pre-compact and save checkpoint before streaming
        history, compact_result = await self._compact_history_if_needed(history)
        if compact_result is not None:
            self._save_compaction_checkpoint(store, sid, compact_result)
            yield CompactEvent(
                original_messages=compact_result.original_messages,
                compacted_messages=compact_result.compacted_messages,
                estimated_tokens_saved=compact_result.estimated_tokens_saved,
                used_llm=compact_result.used_llm,
            ), sid

        store.add_message(sid, "user", prompt_text(prompt), images=prompt_images(prompt) or None)

        async for event in self.run_stream(
            prompt, message_history=history, cancel_event=cancel_event,
            include_tools=include_tools, exclude_tools=exclude_tools,
        ):
            if isinstance(event, DoneEvent):
                store.add_message(sid, "assistant", event.result.output)
            elif isinstance(event, CancelledEvent):
                store.add_message(sid, "assistant", "(cancelled)")
            elif isinstance(event, CircuitBreakerEvent):
                store.add_message(
                    sid, "assistant",
                    f"(circuit breaker: {event.reason})",
                )
            yield event, sid
