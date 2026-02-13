"""Sub-Agent system for task decomposition and parallel execution.

Allows the main agent to spawn specialized sub-agents that run concurrently
and return results back.
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic_ai import Agent

from .config import Config


class AgentType(str, Enum):
    CODE = "code"
    RESEARCH = "research"
    TEST = "test"
    GENERIC = "generic"


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"
    TIMEOUT = "timeout"


@dataclass
class SubAgentResult:
    """Result from a sub-agent execution."""
    agent_id: str
    status: AgentStatus
    output: Optional[str] = None
    error: Optional[str] = None
    created_at: str = ""
    completed_at: Optional[str] = None


# System prompts per agent type
_AGENT_PROMPTS = {
    AgentType.CODE: (
        "You are a coding sub-agent. Focus on writing, modifying, and fixing code. "
        "Be precise and only make the requested changes."
    ),
    AgentType.RESEARCH: (
        "You are a research sub-agent. Analyze code, find patterns, "
        "and provide detailed answers. Do not modify files."
    ),
    AgentType.TEST: (
        "You are a testing sub-agent. Write tests, run test commands, "
        "and report results. Focus on coverage and edge cases."
    ),
    AgentType.GENERIC: (
        "You are a general-purpose sub-agent. Complete the assigned task efficiently."
    ),
}

# Limits
MAX_CONCURRENT_AGENTS = 5
DEFAULT_AGENT_TIMEOUT = 300  # 5 minutes


class SubAgentManager:
    """Manage sub-agent lifecycle with asyncio.

    Usage:
        manager = SubAgentManager(config, workdir)
        agent_id = await manager.spawn("write unit tests", AgentType.TEST)
        status = manager.get_status(agent_id)
        result = await manager.wait(agent_id)
        await manager.cleanup()
    """

    def __init__(
        self,
        config: Config,
        workdir: Path,
        max_concurrent: int = MAX_CONCURRENT_AGENTS,
        default_timeout: float = DEFAULT_AGENT_TIMEOUT,
    ):
        self.config = config
        self.workdir = workdir
        self.max_concurrent = max_concurrent
        self.default_timeout = default_timeout

        self._agents: dict[str, SubAgentResult] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

    # ── Spawn & manage ───────────────────────────────────────────────────────

    async def spawn(
        self,
        task: str,
        agent_type: str = "generic",
        timeout: Optional[float] = None,
    ) -> str:
        """Spawn a sub-agent to handle a task.

        Returns agent_id immediately. The agent runs in the background.
        """
        # Validate type
        try:
            atype = AgentType(agent_type)
        except ValueError:
            atype = AgentType.GENERIC

        # Check limits
        active = sum(
            1 for r in self._agents.values()
            if r.status in (AgentStatus.PENDING, AgentStatus.RUNNING)
        )
        if active >= self.max_concurrent:
            raise RuntimeError(
                f"Agent limit reached ({self.max_concurrent}). "
                "Wait for existing agents to finish or kill one."
            )

        agent_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()

        self._agents[agent_id] = SubAgentResult(
            agent_id=agent_id,
            status=AgentStatus.PENDING,
            created_at=now,
        )

        effective_timeout = timeout or self.default_timeout
        self._tasks[agent_id] = asyncio.create_task(
            self._run_agent(agent_id, task, atype, effective_timeout)
        )

        return agent_id

    def get_status(self, agent_id: str) -> Optional[SubAgentResult]:
        """Get the current status of a sub-agent."""
        return self._agents.get(agent_id)

    async def wait(self, agent_id: str) -> SubAgentResult:
        """Wait for a sub-agent to complete and return its result."""
        task = self._tasks.get(agent_id)
        if task is None:
            result = self._agents.get(agent_id)
            if result is None:
                raise ValueError(f"Unknown agent: {agent_id}")
            return result

        await task
        return self._agents[agent_id]

    async def wait_all(self) -> list[SubAgentResult]:
        """Wait for all running sub-agents."""
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        return list(self._agents.values())

    async def kill(self, agent_id: str) -> bool:
        """Cancel a running sub-agent."""
        task = self._tasks.get(agent_id)
        if task is None or task.done():
            return False

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        self._agents[agent_id].status = AgentStatus.KILLED
        self._agents[agent_id].completed_at = datetime.now(timezone.utc).isoformat()
        return True

    async def cleanup(self) -> None:
        """Cancel all running agents and clean up."""
        for agent_id in list(self._tasks):
            await self.kill(agent_id)
        self._tasks.clear()

    def list_agents(self) -> list[SubAgentResult]:
        """List all agents (active and completed)."""
        return list(self._agents.values())

    # ── Internal ─────────────────────────────────────────────────────────────

    async def _run_agent(
        self,
        agent_id: str,
        task: str,
        agent_type: AgentType,
        timeout: float,
    ) -> None:
        """Execute a sub-agent with timeout and resource limits."""
        async with self._semaphore:
            self._agents[agent_id].status = AgentStatus.RUNNING

            try:
                result = await asyncio.wait_for(
                    self._execute(agent_id, task, agent_type),
                    timeout=timeout,
                )
                self._agents[agent_id].status = AgentStatus.COMPLETED
                self._agents[agent_id].output = result

            except asyncio.TimeoutError:
                self._agents[agent_id].status = AgentStatus.TIMEOUT
                self._agents[agent_id].error = (
                    f"Agent timed out after {timeout}s"
                )

            except asyncio.CancelledError:
                self._agents[agent_id].status = AgentStatus.KILLED
                raise

            except Exception as e:
                self._agents[agent_id].status = AgentStatus.FAILED
                self._agents[agent_id].error = str(e)

            finally:
                self._agents[agent_id].completed_at = (
                    datetime.now(timezone.utc).isoformat()
                )
                self._tasks.pop(agent_id, None)

    async def _execute(
        self,
        agent_id: str,
        task: str,
        agent_type: AgentType,
    ) -> str:
        """Create and run a Pydantic AI agent for the task."""
        from . import tools
        from .runner import CodyDeps
        from .skill_manager import SkillManager

        system_prompt = _AGENT_PROMPTS.get(agent_type, _AGENT_PROMPTS[AgentType.GENERIC])

        agent = Agent(
            self.config.model,
            deps_type=CodyDeps,
            system_prompt=system_prompt,
        )

        # Register a subset of tools based on agent type
        if agent_type in (AgentType.CODE, AgentType.GENERIC):
            agent.tool(tools.read_file)
            agent.tool(tools.write_file)
            agent.tool(tools.edit_file)
            agent.tool(tools.list_directory)
            agent.tool(tools.grep)
            agent.tool(tools.glob)
            agent.tool(tools.patch)
            agent.tool(tools.search_files)
            agent.tool(tools.exec_command)
        elif agent_type == AgentType.RESEARCH:
            agent.tool(tools.read_file)
            agent.tool(tools.list_directory)
            agent.tool(tools.grep)
            agent.tool(tools.glob)
            agent.tool(tools.search_files)
        elif agent_type == AgentType.TEST:
            agent.tool(tools.read_file)
            agent.tool(tools.write_file)
            agent.tool(tools.edit_file)
            agent.tool(tools.list_directory)
            agent.tool(tools.grep)
            agent.tool(tools.glob)
            agent.tool(tools.exec_command)

        deps = CodyDeps(
            config=self.config,
            workdir=self.workdir,
            skill_manager=SkillManager(self.config),
        )

        result = await agent.run(task, deps=deps)
        return result.output
