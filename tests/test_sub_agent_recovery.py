"""Tests for sub-agent recovery (#14)."""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from cody.core.config import Config
from cody.core.sub_agent import (
    AgentStatus,
    SubAgentManager,
)


@pytest.fixture
def config(tmp_path):
    return Config.load(workdir=tmp_path)


@pytest.fixture
def manager(config, tmp_path):
    return SubAgentManager(config=config, workdir=tmp_path)


# ── SubAgentResult stores task/type ─────────────────────────────────────────


class TestResultMetadata:
    @pytest.mark.asyncio
    async def test_spawn_stores_task(self, manager):
        with patch.object(manager, "_execute", new_callable=AsyncMock, return_value="done"):
            agent_id = await manager.spawn("write tests for auth", "test")
            result = await manager.wait(agent_id)
            assert result.task == "write tests for auth"
            assert result.agent_type == "test"

    @pytest.mark.asyncio
    async def test_spawn_stores_generic_default(self, manager):
        with patch.object(manager, "_execute", new_callable=AsyncMock, return_value="done"):
            agent_id = await manager.spawn("do something")
            result = await manager.wait(agent_id)
            assert result.agent_type == "generic"


# ── Resume ──────────────────────────────────────────────────────────────────


class TestResume:
    @pytest.mark.asyncio
    async def test_resume_completed_agent(self, manager):
        """Resuming a completed agent spawns a new one with context."""
        with patch.object(manager, "_execute", new_callable=AsyncMock, return_value="partial result"):
            old_id = await manager.spawn("fix bug in auth.py", "code")
            await manager.wait(old_id)

        with patch.object(manager, "_execute", new_callable=AsyncMock, return_value="full result") :
            new_id = await manager.resume(old_id)
            await manager.wait(new_id)

            assert new_id != old_id
            new_result = manager.get_status(new_id)
            assert new_result.status == AgentStatus.COMPLETED
            assert new_result.output == "full result"

    @pytest.mark.asyncio
    async def test_resume_failed_agent(self, manager):
        """Resuming a failed agent includes error context."""
        async def fail_execute(agent_id, task, agent_type):
            raise RuntimeError("connection timeout")

        with patch.object(manager, "_execute", side_effect=fail_execute):
            old_id = await manager.spawn("deploy to staging", "code")
            await manager.wait(old_id)
            old = manager.get_status(old_id)
            assert old.status == AgentStatus.FAILED
            assert "connection timeout" in old.error

        with patch.object(manager, "_execute", new_callable=AsyncMock, return_value="deployed") :
            new_id = await manager.resume(old_id)
            await manager.wait(new_id)

            # The resumed agent's task should contain original task and error
            new_result = manager.get_status(new_id)
            assert new_result.status == AgentStatus.COMPLETED
            assert "deploy to staging" in new_result.task
            assert "connection timeout" in new_result.task

    @pytest.mark.asyncio
    async def test_resume_timed_out_agent(self, config, tmp_path):
        """Resuming a timed-out agent works."""
        mgr = SubAgentManager(config=config, workdir=tmp_path, default_timeout=0.1)

        async def slow_execute(agent_id, task, agent_type):
            await asyncio.sleep(10)
            return "never"

        with patch.object(mgr, "_execute", side_effect=slow_execute):
            old_id = await mgr.spawn("long task", "generic")
            await mgr.wait(old_id)
            assert mgr.get_status(old_id).status == AgentStatus.TIMEOUT

        with patch.object(mgr, "_execute", new_callable=AsyncMock, return_value="done"):
            new_id = await mgr.resume(old_id)
            await mgr.wait(new_id)
            assert mgr.get_status(new_id).status == AgentStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_resume_preserves_agent_type(self, manager):
        """Resumed agent uses the same type as the original."""
        with patch.object(manager, "_execute", new_callable=AsyncMock, return_value="ok"):
            old_id = await manager.spawn("analyze code", "research")
            await manager.wait(old_id)

        with patch.object(manager, "_execute", new_callable=AsyncMock, return_value="ok"):
            new_id = await manager.resume(old_id)
            await manager.wait(new_id)
            new_result = manager.get_status(new_id)
            assert new_result.agent_type == "research"

    @pytest.mark.asyncio
    async def test_resume_unknown_agent_raises(self, manager):
        with pytest.raises(ValueError, match="Unknown agent"):
            await manager.resume("nonexistent_id")

    @pytest.mark.asyncio
    async def test_resume_running_agent_raises(self, manager):
        never_finish = asyncio.Event()

        async def slow_execute(agent_id, task, agent_type):
            await never_finish.wait()
            return "done"

        with patch.object(manager, "_execute", side_effect=slow_execute):
            agent_id = await manager.spawn("task", "generic")
            # Small delay so agent transitions to RUNNING
            await asyncio.sleep(0.05)

            with pytest.raises(RuntimeError, match="still running"):
                await manager.resume(agent_id)

            # Cleanup
            await manager.kill(agent_id)

    @pytest.mark.asyncio
    async def test_resume_killed_agent_raises(self, manager):
        """Killed agents cannot be resumed."""
        never_finish = asyncio.Event()

        async def slow_execute(agent_id, task, agent_type):
            await never_finish.wait()
            return "done"

        with patch.object(manager, "_execute", side_effect=slow_execute):
            agent_id = await manager.spawn("task", "generic")
            await asyncio.sleep(0.05)
            await manager.kill(agent_id)
            assert manager.get_status(agent_id).status == AgentStatus.KILLED

        with pytest.raises(RuntimeError, match="killed"):
            await manager.resume(agent_id)

    @pytest.mark.asyncio
    async def test_resume_truncates_long_context(self, manager):
        """Nested resume truncates previous output to avoid bloat."""
        long_output = "x" * 5000

        with patch.object(manager, "_execute", new_callable=AsyncMock, return_value=long_output):
            old_id = await manager.spawn("analyze logs", "research")
            await manager.wait(old_id)

        with patch.object(manager, "_execute", new_callable=AsyncMock, return_value="done"):
            new_id = await manager.resume(old_id)
            new_result = manager.get_status(new_id)
            # Task should contain truncated output, not the full 5000 chars
            assert "truncated" in new_result.task
            assert len(new_result.task) < 5000

    @pytest.mark.asyncio
    async def test_resume_includes_previous_output(self, manager):
        """Resume task contains original task and previous output."""
        with patch.object(manager, "_execute", new_callable=AsyncMock, return_value="found 3 bugs"):
            old_id = await manager.spawn("review auth module", "research")
            await manager.wait(old_id)

        with patch.object(manager, "_execute", new_callable=AsyncMock, return_value="fixed all") :
            new_id = await manager.resume(old_id)
            new_result = manager.get_status(new_id)
            # The task should contain the original task and previous output
            assert "review auth module" in new_result.task
            assert "found 3 bugs" in new_result.task


# ── resume_agent tool ───────────────────────────────────────────────────────


class TestResumeAgentTool:
    @pytest.mark.asyncio
    async def test_resume_tool_success(self, manager):
        from cody.core.tools.agents import resume_agent

        with patch.object(manager, "_execute", new_callable=AsyncMock, return_value="done"):
            old_id = await manager.spawn("task", "code")
            await manager.wait(old_id)

        with patch.object(manager, "_execute", new_callable=AsyncMock, return_value="continued"):
            ctx = MagicMock()
            ctx.deps.sub_agent_manager = manager
            result = await resume_agent(ctx, old_id)
            assert "Resumed agent" in result
            assert old_id in result

    @pytest.mark.asyncio
    async def test_resume_tool_unknown_agent(self):
        from cody.core.tools.agents import resume_agent

        ctx = MagicMock()
        ctx.deps.sub_agent_manager = SubAgentManager(
            config=Config(), workdir=MagicMock()
        )
        # resume_agent now lets ValueError propagate (caught by wrapper in production).
        with pytest.raises(ValueError, match="Unknown agent"):
            await resume_agent(ctx, "nonexistent")

    @pytest.mark.asyncio
    async def test_resume_tool_no_manager(self):
        from cody.core.tools.agents import resume_agent

        ctx = MagicMock()
        ctx.deps.sub_agent_manager = None
        result = await resume_agent(ctx, "any_id")
        assert "[ERROR]" in result


# ── Permission registration ─────────────────────────────────────────────────


class TestResumePermission:
    def test_resume_agent_in_default_permissions(self):
        from cody.core.permissions import _DEFAULT_PERMISSIONS
        assert "resume_agent" in _DEFAULT_PERMISSIONS


# ── Tool registration ───────────────────────────────────────────────────────


class TestResumeToolRegistered:
    def test_resume_agent_in_sub_agent_tools(self):
        from cody.core.tools.registry import SUB_AGENT_TOOLS
        from cody.core.tools.agents import resume_agent

        tool_funcs = SUB_AGENT_TOOLS
        assert resume_agent in tool_funcs

    def test_resume_agent_in_core_tools(self):
        from cody.core.tools.registry import CORE_TOOLS
        from cody.core.tools.agents import resume_agent

        assert resume_agent in CORE_TOOLS
