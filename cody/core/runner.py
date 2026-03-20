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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator, Literal, Optional, Union

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ImageUrl,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from .audit import AuditLogger
from .config import Config
from .context import CompactResult, compact_messages, compact_messages_llm
from .deps import CodyDeps
from .file_history import FileHistory
from .log import log_elapsed
from .lsp_client import LSPClient
from .mcp_client import MCPClient
from .permissions import PermissionLevel, PermissionManager
from .prompt import Prompt, prompt_images, prompt_text
from .session import Message, SessionStore
from .skill_manager import SkillManager
from .sub_agent import SubAgentManager
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
class CodyResult:
    """Rich result from the Cody engine.

    The core always provides all information. Upper layers (CLI, TUI, Server)
    decide what to display and how to render it.
    """
    output: str
    thinking: Optional[str] = None
    tool_traces: list[ToolTrace] = field(default_factory=list)
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

        return CodyResult(
            output=raw_result.output,
            thinking="\n\n".join(thinking_parts) if thinking_parts else None,
            tool_traces=tool_traces,
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


StreamEvent = Union[
    SessionStartEvent, CompactEvent, ThinkingEvent, TextDeltaEvent,
    ToolCallEvent, ToolResultEvent, DoneEvent,
    CancelledEvent,
]


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

    def __init__(self, config: Config, workdir: Path, extra_roots: list[Path] | None = None):
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

        # Audit logger
        self._audit_logger = AuditLogger()

        # Permission manager
        self._permission_manager = PermissionManager(
            overrides=self.config.permissions.overrides,
            default_level=PermissionLevel(self.config.permissions.default_level),
        )

        # File history
        self._file_history = FileHistory(workdir=self.workdir)

        # Shared todo list for AI task tracking
        self._todo_list: list = []

        # Create agent
        self.agent = self._create_agent()

    def _resolve_model(self):
        """Resolve model to a Pydantic AI model instance.

        Delegates to model_resolver.resolve_model() which is shared with
        SubAgentManager to keep both in sync.
        """
        return resolve_model(self.config)

    def _create_agent(self) -> Agent:
        """Create Pydantic AI Agent with tools.

        Tools are registered declaratively via tools.register_tools() —
        see tools.py CORE_TOOLS / MCP_TOOLS for the full list.

        System prompt order:
          1. Base persona
          2. CODY.md project instructions (global ~/.cody/CODY.md + project CODY.md)
          3. Available skills XML (Agent Skills standard)
        """
        # 1. Base persona
        system_parts = [
            "You are Cody, an AI coding assistant. "
            "You have access to file operations, shell commands, skills, web search, "
            "and code intelligence via LSP. "
            "When a skill matches the task, call read_skill(skill_name) to load its "
            "full instructions. "
            "For complex tasks with independent parts, use spawn_agent() to run "
            "sub-agents in parallel — see its description for usage guide. "
            "Use webfetch/websearch for web lookups and lsp_* tools for code intelligence. "
            "Always execute commands and file operations as needed to complete tasks.",
        ]

        # 2. CODY.md project instructions (global + project, merged)
        project_instructions = load_project_instructions(self.workdir)
        if project_instructions:
            system_parts.append(
                "## Project Instructions (from CODY.md)\n\n" + project_instructions
            )

        # 3. Available skills
        skills_xml = self.skill_manager.to_prompt_xml()
        if skills_xml:
            system_parts.append(skills_xml)

        agent = Agent(
            self._resolve_model(),
            deps_type=CodyDeps,
            system_prompt="\n\n".join(system_parts),
        )

        tools.register_tools(agent, include_mcp=bool(self._mcp_client))

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

    def _create_deps(self) -> CodyDeps:
        """Create dependencies"""
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

    async def _compact_history_if_needed(
        self,
        history: Optional[list[ModelMessage]],
        max_tokens: int = 100_000,
    ) -> tuple[Optional[list[ModelMessage]], Optional[CompactResult]]:
        """Auto-compact message history when approaching token limits.

        Converts ModelMessage history to dict format, runs compaction,
        then converts back. Returns (history, compact_result_or_none).

        When ``config.compaction.use_llm`` is enabled, uses an LLM agent to
        generate a semantic summary. Falls back to truncation on any error.
        """
        if not history:
            return history, None

        # Convert ModelMessage list → dict list for compaction
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
                    max_tokens=self.config.compaction.max_tokens,
                    keep_recent=self.config.compaction.keep_recent,
                    max_summary_tokens=self.config.compaction.max_summary_tokens,
                )
            except Exception:
                logger.warning(
                    "LLM compaction failed, falling back to truncation",
                    exc_info=True,
                )
                compacted, result = compact_messages(
                    msgs, max_tokens=max_tokens,
                )
        else:
            compacted, result = compact_messages(msgs, max_tokens=max_tokens)

        if result is None:
            return history, None  # no compaction needed

        logger.info(
            "Context compacted: %d → %d messages, ~%d tokens saved (llm=%s)",
            result.original_messages,
            result.compacted_messages,
            result.estimated_tokens_saved,
            result.used_llm,
        )

        # Convert back to ModelMessage format
        # System summary message becomes a user context message
        new_history: list[ModelMessage] = []
        for m in compacted:
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

        return new_history, result

    def _compact_history_sync(
        self,
        history: Optional[list[ModelMessage]],
        max_tokens: int = 100_000,
    ) -> tuple[Optional[list[ModelMessage]], Optional[CompactResult]]:
        """Synchronous compaction — always uses truncation (no LLM)."""
        if not history:
            return history, None

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

        compacted, result = compact_messages(msgs, max_tokens=max_tokens)
        if result is None:
            return history, None

        new_history: list[ModelMessage] = []
        for m in compacted:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "system":
                new_history.append(
                    ModelRequest(
                        parts=[UserPromptPart(content=f"[Context]\n{content}")]
                    )
                )
            elif role == "user":
                new_history.append(
                    ModelRequest(parts=[UserPromptPart(content=content)])
                )
            elif role == "assistant":
                new_history.append(
                    ModelResponse(parts=[TextPart(content=content)])
                )

        return new_history, result

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
    ) -> CodyResult:
        """Run agent with prompt, optionally continuing from history"""
        deps = self._create_deps()
        message_history, _compact = await self._compact_history_if_needed(message_history)
        pydantic_prompt = self._to_pydantic_prompt(prompt)
        result = await self.agent.run(  # type: ignore[call-overload]
            pydantic_prompt, deps=deps, message_history=message_history,
            model_settings=self._build_model_settings(),
        )
        return CodyResult.from_raw(result)

    @log_elapsed("AgentRunner.run_stream", level=logging.INFO)
    async def run_stream(
        self,
        prompt: Prompt,
        message_history: Optional[list[ModelMessage]] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Run agent with streaming, yielding structured StreamEvent objects.

        Events:
          - CompactEvent: context was auto-compacted (first event if applicable)
          - ThinkingEvent: incremental thinking content
          - TextDeltaEvent: incremental text output
          - ToolCallEvent: tool call initiated
          - ToolResultEvent: tool call result
          - DoneEvent: stream complete with full CodyResult
          - CancelledEvent: run was cancelled via cancel_event
        """
        from pydantic_ai.messages import (
            PartStartEvent,
            PartDeltaEvent,
            FunctionToolCallEvent,
            FunctionToolResultEvent,
        )
        from pydantic_ai.run import AgentRunResultEvent

        deps = self._create_deps()
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
        async for event in self.agent.run_stream_events(  # type: ignore[call-overload]
            pydantic_prompt, deps=deps, message_history=message_history,
            model_settings=self._build_model_settings(),
        ):
            if cancel_event and cancel_event.is_set():
                yield CancelledEvent()
                return

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

            elif isinstance(event, FunctionToolCallEvent):
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

            elif isinstance(event, AgentRunResultEvent):
                cody_result = CodyResult.from_raw(event.result)
                yield DoneEvent(result=cody_result)

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
        deps = self._create_deps()
        if self.config.compaction.use_llm:
            logger.debug(
                "LLM compaction unavailable in run_sync, using truncation"
            )
        message_history, _compact = self._compact_history_sync(message_history)
        pydantic_prompt = self._to_pydantic_prompt(prompt)
        result = self.agent.run_sync(  # type: ignore[call-overload]
            pydantic_prompt, deps=deps, message_history=message_history,
            model_settings=self._build_model_settings(),
        )
        return CodyResult.from_raw(result)

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

        result = await self.run(prompt, message_history=history)
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

        async for event in self.run_stream(prompt, message_history=history, cancel_event=cancel_event):
            if isinstance(event, DoneEvent):
                store.add_message(sid, "assistant", event.result.output)
            elif isinstance(event, CancelledEvent):
                store.add_message(sid, "assistant", "(cancelled)")
            yield event, sid
