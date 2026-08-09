"""Tests for UserInputQueue and proactive user input injection."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pydantic_ai import FunctionToolCallEvent, FunctionToolResultEvent
from pydantic_ai.messages import ToolCallPart, ToolReturnPart

from cody.core.user_input import UserInputQueue
from cody.core.runner import ToolResultEvent, UserInputReceivedEvent


# ── UserInputQueue ──────────────────────────────────────────────────────────


def test_queue_empty_try_get():
    q = UserInputQueue()
    assert q.try_get() is None


def test_queue_empty_drain_all():
    q = UserInputQueue()
    assert q.drain_all() == []


@pytest.mark.asyncio
async def test_queue_put_and_try_get():
    q = UserInputQueue()
    await q.put("hello")
    assert q.try_get() == "hello"
    assert q.try_get() is None


@pytest.mark.asyncio
async def test_queue_put_and_drain_all():
    q = UserInputQueue()
    await q.put("one")
    await q.put("two")
    await q.put("three")
    assert q.drain_all() == ["one", "two", "three"]
    assert q.drain_all() == []


@pytest.mark.asyncio
async def test_queue_drain_preserves_order():
    q = UserInputQueue()
    for i in range(10):
        await q.put(f"msg-{i}")
    drained = q.drain_all()
    assert drained == [f"msg-{i}" for i in range(10)]


# ── UserInputReceivedEvent ────────────────────────────────────────────────


def test_event_fields():
    evt = UserInputReceivedEvent(content="test message")
    assert evt.content == "test message"
    assert evt.event_type == "user_input_received"


# ── AgentRunner.inject_user_input ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_inject_user_input_queues_message(tmp_path):
    """inject_user_input() puts message into the internal queue."""
    from unittest.mock import patch

    from cody.core.config import Config

    config = Config(model="test", model_base_url="http://fake", model_api_key="fake")

    with patch("cody.core.runner.Agent"):
        from cody.core.runner import AgentRunner
        runner = AgentRunner(config=config, workdir=tmp_path)

    await runner.inject_user_input("hello from user")
    assert runner._user_input_queue.try_get() == "hello from user"


@pytest.mark.asyncio
async def test_inject_multiple_messages(tmp_path):
    """Multiple inject calls queue all messages."""
    from unittest.mock import patch

    from cody.core.config import Config

    config = Config(model="test", model_base_url="http://fake", model_api_key="fake")

    with patch("cody.core.runner.Agent"):
        from cody.core.runner import AgentRunner
        runner = AgentRunner(config=config, workdir=tmp_path)

    await runner.inject_user_input("msg1")
    await runner.inject_user_input("msg2")
    assert runner._user_input_queue.drain_all() == ["msg1", "msg2"]


@pytest.mark.asyncio
async def test_input_injected_after_tool_result_reaches_next_model_request(tmp_path):
    """The tool producer must wait for consumers to inject at the boundary."""
    from cody.core.config import Config
    from cody.core.runner import AgentRunner

    config = Config(model="test", model_base_url="http://fake", model_api_key="fake")
    with patch("cody.core.runner.Agent"):
        runner = AgentRunner(config=config, workdir=tmp_path)

    class FakeCallToolsNode:
        user_prompt = None
        prompt_seen_at_completion = None

        @asynccontextmanager
        async def stream(self, _ctx):
            async def events():
                yield FunctionToolCallEvent(
                    ToolCallPart("probe", {}, tool_call_id="call-1")
                )
                yield FunctionToolResultEvent(
                    ToolReturnPart("probe", "PROBE_OK", tool_call_id="call-1")
                )
                self.prompt_seen_at_completion = self.user_prompt

            yield events()

    node = FakeCallToolsNode()
    seen = []
    async for event in runner._stream_tool_node(
        node,
        SimpleNamespace(ctx=None),
        asyncio.Queue(),
        lambda: [],
    ):
        seen.append(event)
        if isinstance(event, ToolResultEvent):
            await runner.inject_user_input("DO_THE_NEXT_STEP")

    assert any(isinstance(event, UserInputReceivedEvent) for event in seen)
    assert node.user_prompt == "DO_THE_NEXT_STEP"
    assert node.prompt_seen_at_completion == "DO_THE_NEXT_STEP"
