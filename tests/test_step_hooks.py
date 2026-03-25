"""Tests for step hook / middleware (#11)."""

import pytest
from unittest.mock import MagicMock, patch

from pydantic_ai import RunContext

from cody.core.config import Config
from cody.core.deps import CodyDeps
from cody.core.runner import AgentRunner
from cody.core.skill_manager import SkillManager
from cody.core.tools._base import _with_model_retry


# ── Sample tool for testing ──────────────────────────────────────────────────


async def sample_tool(ctx: RunContext[CodyDeps], query: str) -> str:
    """A sample tool that echoes the query."""
    return f"result:{query}"


# ── Mock context helper ──────────────────────────────────────────────────────


class _MockCtx:
    def __init__(self, deps):
        self.deps = deps


def _make_deps(
    tmp_path,
    before_hooks=None,
    after_hooks=None,
) -> CodyDeps:
    config = Config()
    return CodyDeps(
        config=config,
        workdir=tmp_path,
        skill_manager=SkillManager(config, workdir=tmp_path),
        before_tool_hooks=before_hooks or [],
        after_tool_hooks=after_hooks or [],
    )


# ── _with_model_retry hook integration ───────────────────────────────────────


class TestBeforeToolHook:
    @pytest.mark.asyncio
    async def test_before_hook_called(self, tmp_path):
        """before_tool hook is called with tool name and args."""
        calls = []

        async def hook(tool_name, args):
            calls.append((tool_name, args))
            return args  # proceed

        deps = _make_deps(tmp_path, before_hooks=[hook])
        ctx = _MockCtx(deps)
        wrapped = _with_model_retry(sample_tool)
        result = await wrapped(ctx, query="hello")
        assert result == "result:hello"
        assert calls == [("sample_tool", {"query": "hello"})]

    @pytest.mark.asyncio
    async def test_before_hook_modifies_args(self, tmp_path):
        """before_tool hook can modify args."""
        async def hook(tool_name, args):
            args["query"] = "modified"
            return args

        deps = _make_deps(tmp_path, before_hooks=[hook])
        ctx = _MockCtx(deps)
        wrapped = _with_model_retry(sample_tool)
        result = await wrapped(ctx, query="original")
        assert result == "result:modified"

    @pytest.mark.asyncio
    async def test_before_hook_rejects(self, tmp_path):
        """before_tool hook returning None rejects the call."""
        from pydantic_ai import ModelRetry

        async def hook(tool_name, args):
            return None  # reject

        deps = _make_deps(tmp_path, before_hooks=[hook])
        ctx = _MockCtx(deps)
        wrapped = _with_model_retry(sample_tool)
        with pytest.raises(ModelRetry, match="rejected"):
            await wrapped(ctx, query="hello")

    @pytest.mark.asyncio
    async def test_multiple_before_hooks(self, tmp_path):
        """Multiple before hooks run in order."""
        order = []

        async def hook1(tool_name, args):
            order.append("hook1")
            args["query"] = args["query"] + "_1"
            return args

        async def hook2(tool_name, args):
            order.append("hook2")
            args["query"] = args["query"] + "_2"
            return args

        deps = _make_deps(tmp_path, before_hooks=[hook1, hook2])
        ctx = _MockCtx(deps)
        wrapped = _with_model_retry(sample_tool)
        result = await wrapped(ctx, query="x")
        assert result == "result:x_1_2"
        assert order == ["hook1", "hook2"]


class TestAfterToolHook:
    @pytest.mark.asyncio
    async def test_after_hook_called(self, tmp_path):
        """after_tool hook is called with tool name, args, and result."""
        calls = []

        async def hook(tool_name, args, result):
            calls.append((tool_name, args, result))
            return result

        deps = _make_deps(tmp_path, after_hooks=[hook])
        ctx = _MockCtx(deps)
        wrapped = _with_model_retry(sample_tool)
        result = await wrapped(ctx, query="test")
        assert result == "result:test"
        assert len(calls) == 1
        assert calls[0][0] == "sample_tool"
        assert calls[0][2] == "result:test"

    @pytest.mark.asyncio
    async def test_after_hook_modifies_result(self, tmp_path):
        """after_tool hook can modify the result."""
        async def hook(tool_name, args, result):
            return result.upper()

        deps = _make_deps(tmp_path, after_hooks=[hook])
        ctx = _MockCtx(deps)
        wrapped = _with_model_retry(sample_tool)
        result = await wrapped(ctx, query="hello")
        assert result == "RESULT:HELLO"

    @pytest.mark.asyncio
    async def test_multiple_after_hooks(self, tmp_path):
        """Multiple after hooks chain results."""
        async def hook1(tool_name, args, result):
            return result + " [hook1]"

        async def hook2(tool_name, args, result):
            return result + " [hook2]"

        deps = _make_deps(tmp_path, after_hooks=[hook1, hook2])
        ctx = _MockCtx(deps)
        wrapped = _with_model_retry(sample_tool)
        result = await wrapped(ctx, query="x")
        assert result == "result:x [hook1] [hook2]"


class TestNoHooks:
    @pytest.mark.asyncio
    async def test_no_hooks_normal_execution(self, tmp_path):
        """Without hooks, tool executes normally."""
        deps = _make_deps(tmp_path)
        ctx = _MockCtx(deps)
        wrapped = _with_model_retry(sample_tool)
        result = await wrapped(ctx, query="hello")
        assert result == "result:hello"


# ── Runner-level tests ───────────────────────────────────────────────────────


class TestRunnerHooks:
    def test_runner_stores_hooks(self, tmp_path):
        """AgentRunner stores hooks."""
        async def hook(n, a):
            return a

        with patch.object(AgentRunner, "_create_agent", return_value=MagicMock()):
            runner = AgentRunner(
                config=Config(), workdir=tmp_path,
                before_tool_hooks=[hook],
                after_tool_hooks=[hook],
            )
        assert runner._before_tool_hooks == [hook]
        assert runner._after_tool_hooks == [hook]

    def test_runner_default_no_hooks(self, tmp_path):
        """Without hooks, lists are empty."""
        with patch.object(AgentRunner, "_create_agent", return_value=MagicMock()):
            runner = AgentRunner(config=Config(), workdir=tmp_path)
        assert runner._before_tool_hooks == []
        assert runner._after_tool_hooks == []


# ── SDK Builder-level tests ──────────────────────────────────────────────────


class TestBuilderHooks:
    def test_before_tool_method(self):
        from cody.sdk.client import CodyBuilder
        async def hook(n, a):
            return a
        builder = CodyBuilder()
        result = builder.before_tool(hook)
        assert result is builder
        assert hook in builder._before_tool_hooks

    def test_after_tool_method(self):
        from cody.sdk.client import CodyBuilder
        async def hook(n, a, r):
            return r
        builder = CodyBuilder()
        result = builder.after_tool(hook)
        assert result is builder
        assert hook in builder._after_tool_hooks

    def test_builder_passes_hooks_to_client(self):
        from cody.sdk.client import Cody, AsyncCodyClient
        async def bh(n, a):
            return a
        async def ah(n, a, r):
            return r
        with patch.object(AsyncCodyClient, "__init__", return_value=None) as mock_init:
            Cody().before_tool(bh).after_tool(ah).build()
            _, kwargs = mock_init.call_args
            assert kwargs["before_tool_hooks"] == [bh]
            assert kwargs["after_tool_hooks"] == [ah]
