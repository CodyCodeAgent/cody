"""Tests for non-streaming run() cancellation (#10)."""

import asyncio

import pytest
from unittest.mock import MagicMock, patch

from cody.core.config import Config
from cody.core.runner import AgentRunner, CodyResult


@pytest.mark.asyncio
async def test_run_cancel_event_triggers(tmp_path):
    """When cancel_event is set before run starts, it returns (cancelled)."""
    with patch.object(AgentRunner, "_create_agent", return_value=MagicMock()):
        runner = AgentRunner(config=Config(), workdir=tmp_path)

    # Create a cancel event that is already set
    cancel_event = asyncio.Event()
    cancel_event.set()

    # Mock the agent.run to simulate a long-running task
    async def slow_run(*args, **kwargs):
        await asyncio.sleep(10)
        return MagicMock()

    runner.agent = MagicMock()
    runner.agent.run = slow_run

    result = await runner.run("test prompt", cancel_event=cancel_event)
    assert result.output == "(cancelled)"


@pytest.mark.asyncio
async def test_run_cancel_event_during_run(tmp_path):
    """cancel_event set during run returns (cancelled)."""
    with patch.object(AgentRunner, "_create_agent", return_value=MagicMock()):
        runner = AgentRunner(config=Config(), workdir=tmp_path)

    cancel_event = asyncio.Event()

    async def slow_run(*args, **kwargs):
        await asyncio.sleep(10)
        return MagicMock()

    runner.agent = MagicMock()
    runner.agent.run = slow_run

    # Set cancel after a short delay
    async def cancel_soon():
        await asyncio.sleep(0.05)
        cancel_event.set()

    cancel_task = asyncio.create_task(cancel_soon())
    result = await runner.run("test prompt", cancel_event=cancel_event)
    assert result.output == "(cancelled)"
    cancel_task.cancel()


@pytest.mark.asyncio
async def test_run_without_cancel_event(tmp_path):
    """Without cancel_event, run completes normally."""
    with patch.object(AgentRunner, "_create_agent", return_value=MagicMock()):
        runner = AgentRunner(config=Config(), workdir=tmp_path)

    mock_result = MagicMock()
    mock_result.output = "done"
    mock_result.all_messages.return_value = []
    mock_result.usage.return_value = MagicMock(total_tokens=100)

    async def quick_run(*args, **kwargs):
        return mock_result

    runner.agent = MagicMock()
    runner.agent.run = quick_run

    with patch.object(CodyResult, "from_raw", return_value=CodyResult(output="done")):
        result = await runner.run("test prompt")
    assert result.output == "done"


@pytest.mark.asyncio
async def test_run_cancel_event_not_set(tmp_path):
    """cancel_event provided but never set — run completes normally."""
    with patch.object(AgentRunner, "_create_agent", return_value=MagicMock()):
        runner = AgentRunner(config=Config(), workdir=tmp_path)

    cancel_event = asyncio.Event()  # Not set

    mock_result = MagicMock()
    mock_result.output = "done"
    mock_result.all_messages.return_value = []
    mock_result.usage.return_value = MagicMock(total_tokens=100)

    async def quick_run(*args, **kwargs):
        return mock_result

    runner.agent = MagicMock()
    runner.agent.run = quick_run

    with patch.object(CodyResult, "from_raw", return_value=CodyResult(output="done")):
        result = await runner.run("test prompt", cancel_event=cancel_event)
    assert result.output == "done"


# ── SDK Builder-level test ───────────────────────────────────────────────────


class TestSDKRunCancel:
    def test_run_overload_accepts_cancel_event(self):
        """SDK run() signature accepts cancel_event."""
        from cody.sdk.client import AsyncCodyClient
        import inspect
        sig = inspect.signature(AsyncCodyClient.run)
        assert "cancel_event" in sig.parameters
