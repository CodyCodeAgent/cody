"""Tests for Sub-Agent system"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from cody.core.config import Config
from cody.core.sub_agent import (
    AgentStatus,
    AgentType,
    SubAgentManager,
    SubAgentResult,
    MAX_CONCURRENT_AGENTS,
    DEFAULT_AGENT_TIMEOUT,
)


@pytest.fixture
def config(tmp_path):
    return Config.load(workdir=tmp_path)


@pytest.fixture
def manager(config, tmp_path):
    return SubAgentManager(config=config, workdir=tmp_path)


# ── AgentType enum ──────────────────────────────────────────────────────────


def test_agent_type_values():
    assert AgentType.CODE == "code"
    assert AgentType.RESEARCH == "research"
    assert AgentType.TEST == "test"
    assert AgentType.GENERIC == "generic"


def test_agent_type_from_string():
    assert AgentType("code") == AgentType.CODE
    assert AgentType("generic") == AgentType.GENERIC


def test_agent_type_invalid():
    with pytest.raises(ValueError):
        AgentType("invalid_type")


# ── AgentStatus enum ───────────────────────────────────────────────────────


def test_agent_status_values():
    assert AgentStatus.PENDING == "pending"
    assert AgentStatus.RUNNING == "running"
    assert AgentStatus.COMPLETED == "completed"
    assert AgentStatus.FAILED == "failed"
    assert AgentStatus.KILLED == "killed"
    assert AgentStatus.TIMEOUT == "timeout"


# ── SubAgentManager init ───────────────────────────────────────────────────


def test_manager_init(config, tmp_path):
    mgr = SubAgentManager(config=config, workdir=tmp_path)
    assert mgr.max_concurrent == MAX_CONCURRENT_AGENTS
    assert mgr.default_timeout == DEFAULT_AGENT_TIMEOUT
    assert mgr.list_agents() == []


def test_manager_custom_limits(config, tmp_path):
    mgr = SubAgentManager(
        config=config,
        workdir=tmp_path,
        max_concurrent=2,
        default_timeout=60,
    )
    assert mgr.max_concurrent == 2
    assert mgr.default_timeout == 60


# ── Spawn ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_spawn_returns_id(manager):
    """Spawn creates agent with valid ID"""
    with patch.object(manager, "_execute", new_callable=AsyncMock, return_value="done"):
        agent_id = await manager.spawn("hello", "generic")
        assert len(agent_id) == 12

        # Wait for it
        result = await manager.wait(agent_id)
        assert result.status == AgentStatus.COMPLETED
        assert result.output == "done"


@pytest.mark.asyncio
async def test_spawn_invalid_type_defaults_to_generic(manager):
    """Invalid type falls back to generic"""
    with patch.object(manager, "_execute", new_callable=AsyncMock, return_value="ok"):
        agent_id = await manager.spawn("task", "nonexistent_type")
        result = await manager.wait(agent_id)
        assert result.status == AgentStatus.COMPLETED


@pytest.mark.asyncio
async def test_spawn_limit_reached(config, tmp_path):
    """Exceeding max_concurrent raises RuntimeError"""
    mgr = SubAgentManager(config=config, workdir=tmp_path, max_concurrent=1)

    never_finish = asyncio.Event()

    async def slow_execute(agent_id, task, agent_type):
        await never_finish.wait()
        return "done"

    with patch.object(mgr, "_execute", side_effect=slow_execute):
        await mgr.spawn("task1", "generic")
        # Second spawn should fail
        with pytest.raises(RuntimeError, match="limit reached"):
            await mgr.spawn("task2", "generic")

    await mgr.cleanup()


# ── Get status ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_status_unknown(manager):
    assert manager.get_status("unknown") is None


@pytest.mark.asyncio
async def test_get_status_pending(manager):
    """Immediately after spawn, status is pending or running"""
    with patch.object(manager, "_execute", new_callable=AsyncMock, return_value="done"):
        agent_id = await manager.spawn("task", "generic")
        result = manager.get_status(agent_id)
        assert result is not None
        assert result.agent_id == agent_id
        await manager.wait(agent_id)


# ── Wait ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wait_unknown(manager):
    with pytest.raises(ValueError, match="Unknown agent"):
        await manager.wait("unknown_id")


@pytest.mark.asyncio
async def test_wait_all(manager):
    with patch.object(manager, "_execute", new_callable=AsyncMock, return_value="done"):
        await manager.spawn("task1")
        await manager.spawn("task2")

        results = await manager.wait_all()
        assert len(results) == 2
        for r in results:
            assert r.status == AgentStatus.COMPLETED


# ── Kill ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_kill_completed(manager):
    """Kill on a completed agent returns False"""
    with patch.object(manager, "_execute", new_callable=AsyncMock, return_value="done"):
        agent_id = await manager.spawn("task")
        await manager.wait(agent_id)

    killed = await manager.kill(agent_id)
    assert killed is False


@pytest.mark.asyncio
async def test_kill_unknown(manager):
    killed = await manager.kill("unknown")
    assert killed is False


@pytest.mark.asyncio
async def test_kill_running(manager):
    """Kill a running agent"""
    started = asyncio.Event()
    block = asyncio.Event()

    async def slow_execute(agent_id, task, agent_type):
        started.set()
        await block.wait()
        return "done"

    with patch.object(manager, "_execute", side_effect=slow_execute):
        agent_id = await manager.spawn("long task")
        await started.wait()

        killed = await manager.kill(agent_id)
        assert killed is True
        status = manager.get_status(agent_id)
        assert status.status == AgentStatus.KILLED


# ── Timeout ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_timeout(config, tmp_path):
    mgr = SubAgentManager(config=config, workdir=tmp_path, default_timeout=0.1)

    async def slow_execute(agent_id, task, agent_type):
        await asyncio.sleep(10)
        return "done"

    with patch.object(mgr, "_execute", side_effect=slow_execute):
        agent_id = await mgr.spawn("slow task")
        result = await mgr.wait(agent_id)

    assert result.status == AgentStatus.TIMEOUT
    assert "timed out" in result.error


# ── Failure ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_failure(manager):
    async def failing_execute(agent_id, task, agent_type):
        raise RuntimeError("agent crashed")

    with patch.object(manager, "_execute", side_effect=failing_execute):
        agent_id = await manager.spawn("bad task")
        result = await manager.wait(agent_id)

    assert result.status == AgentStatus.FAILED
    assert "agent crashed" in result.error


# ── Cleanup ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cleanup(manager):
    """Cleanup cancels all running agents"""
    block = asyncio.Event()

    async def slow_execute(agent_id, task, agent_type):
        await block.wait()
        return "done"

    with patch.object(manager, "_execute", side_effect=slow_execute):
        await manager.spawn("task1")
        await manager.spawn("task2")

    await manager.cleanup()

    for r in manager.list_agents():
        assert r.status == AgentStatus.KILLED


# ── List agents ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_agents(manager):
    with patch.object(manager, "_execute", new_callable=AsyncMock, return_value="done"):
        await manager.spawn("t1")
        await manager.spawn("t2")
        await manager.wait_all()

    agents = manager.list_agents()
    assert len(agents) == 2
    assert all(a.status == AgentStatus.COMPLETED for a in agents)


# ── SubAgentResult ──────────────────────────────────────────────────────────


def test_sub_agent_result_fields():
    r = SubAgentResult(
        agent_id="abc123",
        status=AgentStatus.COMPLETED,
        output="done",
        created_at="2026-01-01",
        completed_at="2026-01-01",
    )
    assert r.agent_id == "abc123"
    assert r.status == AgentStatus.COMPLETED
    assert r.output == "done"
    assert r.error is None
