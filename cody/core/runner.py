"""Agent runner - core execution engine"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from .audit import AuditLogger
from .config import Config
from .file_history import FileHistory
from .lsp_client import LSPClient
from .mcp_client import MCPClient
from .permissions import PermissionLevel, PermissionManager
from .session import Message, SessionStore
from .skill_manager import SkillManager
from .sub_agent import SubAgentManager
from . import tools


@dataclass
class CodyDeps:
    """Dependencies for Cody Agent"""
    config: Config
    workdir: Path
    skill_manager: SkillManager
    mcp_client: Optional[MCPClient] = None
    sub_agent_manager: Optional[SubAgentManager] = None
    lsp_client: Optional[LSPClient] = None
    audit_logger: Optional[AuditLogger] = None
    permission_manager: Optional[PermissionManager] = None
    file_history: Optional[FileHistory] = None


class AgentRunner:
    """Run Cody Agent with full context"""

    def __init__(self, config: Optional[Config] = None, workdir: Optional[Path] = None):
        self.config = config or Config.load()
        self.workdir = Path(workdir) if workdir else Path.cwd()
        self.skill_manager = SkillManager(self.config)

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

        # Create agent
        self.agent = self._create_agent()

    def _create_agent(self) -> Agent:
        """Create Pydantic AI Agent with tools"""
        agent = Agent(
            self.config.model,
            deps_type=CodyDeps,
            system_prompt=(
                "You are Cody, an AI coding assistant. "
                "You have access to file operations, shell commands, skills, web search, "
                "and code intelligence via LSP. "
                "When you need to use a skill, first call list_skills() to see what's available, "
                "then call read_skill(skill_name) to learn how to use it. "
                "For complex tasks, you can spawn sub-agents using spawn_agent(). "
                "Use webfetch/websearch for web lookups and lsp_* tools for code intelligence. "
                "Always execute commands and file operations as needed to complete tasks."
            ),
        )

        # Register tools — file operations
        agent.tool(tools.read_file)
        agent.tool(tools.write_file)
        agent.tool(tools.edit_file)
        agent.tool(tools.list_directory)
        # Search tools
        agent.tool(tools.grep)
        agent.tool(tools.glob)
        agent.tool(tools.patch)
        agent.tool(tools.search_files)
        # Command execution
        agent.tool(tools.exec_command)
        # Skill discovery
        agent.tool(tools.list_skills)
        agent.tool(tools.read_skill)

        # Sub-agent tools
        agent.tool(tools.spawn_agent)
        agent.tool(tools.get_agent_status)
        agent.tool(tools.kill_agent)

        # MCP tool (dynamic proxy)
        if self._mcp_client:
            agent.tool(tools.mcp_call)
            agent.tool(tools.mcp_list_tools)

        # Web tools
        agent.tool(tools.webfetch)
        agent.tool(tools.websearch)

        # LSP tools
        agent.tool(tools.lsp_diagnostics)
        agent.tool(tools.lsp_definition)
        agent.tool(tools.lsp_references)
        agent.tool(tools.lsp_hover)

        # File history tools
        agent.tool(tools.undo_file)
        agent.tool(tools.redo_file)
        agent.tool(tools.list_file_changes)

        return agent

    def _create_deps(self) -> CodyDeps:
        """Create dependencies"""
        return CodyDeps(
            config=self.config,
            workdir=self.workdir,
            skill_manager=self.skill_manager,
            mcp_client=self._mcp_client,
            sub_agent_manager=self._sub_agent_manager,
            lsp_client=self._lsp_client,
            audit_logger=self._audit_logger,
            permission_manager=self._permission_manager,
            file_history=self._file_history,
        )

    # ── MCP lifecycle ────────────────────────────────────────────────────────

    async def start_mcp(self) -> None:
        """Start MCP servers if configured."""
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

        Returns (session_id, history_or_none).
        """
        if session_id:
            session = store.get_session(session_id)
            if not session:
                raise ValueError(f"Session not found: {session_id}")
            history = self.messages_to_history(session.messages) if session.messages else None
            return session.id, history

        session = store.create_session(
            model=self.config.model,
            workdir=str(self.workdir),
        )
        return session.id, None

    # ── Core run methods ─────────────────────────────────────────────────────

    async def run(
        self,
        prompt: str,
        message_history: Optional[list[ModelMessage]] = None,
    ):
        """Run agent with prompt, optionally continuing from history"""
        deps = self._create_deps()
        result = await self.agent.run(prompt, deps=deps, message_history=message_history)
        return result

    async def run_stream(
        self,
        prompt: str,
        message_history: Optional[list[ModelMessage]] = None,
    ):
        """Run agent with streaming"""
        deps = self._create_deps()
        async with self.agent.run_stream(
            prompt, deps=deps, message_history=message_history
        ) as result:
            async for text in result.stream_text():
                yield text

    def run_sync(
        self,
        prompt: str,
        message_history: Optional[list[ModelMessage]] = None,
    ):
        """Run agent synchronously"""
        deps = self._create_deps()
        result = self.agent.run_sync(prompt, deps=deps, message_history=message_history)
        return result

    # ── Session-aware run methods ────────────────────────────────────────────

    async def run_with_session(
        self,
        prompt: str,
        store: SessionStore,
        session_id: Optional[str] = None,
    ) -> tuple[object, str]:
        """Run agent with automatic session persistence.

        Returns (result, session_id). Creates a new session if session_id is None.
        """
        sid, history = self.prepare_session(store, session_id)
        result = await self.run(prompt, message_history=history)
        store.add_message(sid, "user", prompt)
        store.add_message(sid, "assistant", result.output)
        return result, sid

    async def run_stream_with_session(
        self,
        prompt: str,
        store: SessionStore,
        session_id: Optional[str] = None,
    ):
        """Stream agent with automatic session persistence.

        Yields text chunks. Saves user+assistant messages after stream completes.
        Returns are yielded as (chunk, session_id) — session_id is in the first yield.
        """
        sid, history = self.prepare_session(store, session_id)
        store.add_message(sid, "user", prompt)

        chunks: list[str] = []
        deps = self._create_deps()
        async with self.agent.run_stream(
            prompt, deps=deps, message_history=history
        ) as result:
            async for text in result.stream_text():
                chunks.append(text)
                yield text, sid

        full_output = "".join(chunks)
        store.add_message(sid, "assistant", full_output)
