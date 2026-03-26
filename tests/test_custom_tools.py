"""Tests for custom tool registration API (#7)."""

from unittest.mock import MagicMock, patch

from pydantic_ai import RunContext

from cody.core.config import Config
from cody.core.deps import CodyDeps
from cody.core.runner import AgentRunner
from cody.core.tools.registry import register_tools


# ── Sample custom tools for testing ──────────────────────────────────────────


async def my_custom_tool(ctx: RunContext[CodyDeps], query: str) -> str:
    """A test custom tool.

    Args:
        query: Search query.
    """
    return f"custom_result: {query}"


async def another_tool(ctx: RunContext[CodyDeps], x: int, y: int) -> str:
    """Another custom tool that adds two numbers.

    Args:
        x: First number.
        y: Second number.
    """
    return str(x + y)


# ── Registry-level tests ─────────────────────────────────────────────────────


class TestRegisterCustomTools:
    def test_register_without_custom_tools(self):
        """Existing behavior: no custom tools, no error."""
        agent = MagicMock()
        agent.tool.return_value = lambda f: f
        register_tools(agent)
        # Should have been called for each CORE_TOOL
        assert agent.tool.call_count > 0

    def test_register_with_custom_tools(self):
        """Custom tools are registered alongside core tools."""
        agent = MagicMock()
        agent.tool.return_value = lambda f: f
        register_tools(agent, custom_tools=[my_custom_tool, another_tool])
        # Total calls = CORE_TOOLS count + 2 custom tools
        from cody.core.tools.registry import CORE_TOOLS
        expected = len(CORE_TOOLS) + 2
        assert agent.tool.call_count == expected

    def test_register_with_empty_list(self):
        """Empty custom_tools list behaves like None."""
        agent = MagicMock()
        agent.tool.return_value = lambda f: f
        register_tools(agent, custom_tools=[])
        from cody.core.tools.registry import CORE_TOOLS
        assert agent.tool.call_count == len(CORE_TOOLS)

    def test_register_with_none(self):
        """None custom_tools behaves like default."""
        agent = MagicMock()
        agent.tool.return_value = lambda f: f
        register_tools(agent, custom_tools=None)
        from cody.core.tools.registry import CORE_TOOLS
        assert agent.tool.call_count == len(CORE_TOOLS)


# ── Runner-level tests ───────────────────────────────────────────────────────


class TestRunnerCustomTools:
    def test_runner_stores_custom_tools(self, tmp_path):
        """AgentRunner stores custom_tools for agent creation."""
        with patch.object(AgentRunner, "_create_agent", return_value=MagicMock()):
            runner = AgentRunner(
                config=Config(),
                workdir=tmp_path,
                custom_tools=[my_custom_tool],
            )
        assert runner._custom_tools == [my_custom_tool]

    def test_runner_default_no_custom_tools(self, tmp_path):
        """Without custom_tools, list is empty."""
        with patch.object(AgentRunner, "_create_agent", return_value=MagicMock()):
            runner = AgentRunner(config=Config(), workdir=tmp_path)
        assert runner._custom_tools == []


# ── SDK Builder-level tests ──────────────────────────────────────────────────


class TestBuilderCustomTools:
    def test_builder_tool_method(self):
        """Builder.tool() appends to custom tools list."""
        from cody.sdk.client import CodyBuilder
        builder = CodyBuilder()
        result = builder.tool(my_custom_tool)
        assert result is builder  # fluent interface
        assert my_custom_tool in builder._custom_tools

    def test_builder_multiple_tools(self):
        """Multiple tool() calls accumulate."""
        from cody.sdk.client import CodyBuilder
        builder = CodyBuilder()
        builder.tool(my_custom_tool).tool(another_tool)
        assert len(builder._custom_tools) == 2
        assert builder._custom_tools == [my_custom_tool, another_tool]

    def test_builder_passes_tools_to_client(self):
        """build() passes custom tools to AsyncCodyClient."""
        from cody.sdk.client import Cody, AsyncCodyClient
        with patch.object(AsyncCodyClient, "__init__", return_value=None) as mock_init:
            Cody().tool(my_custom_tool).tool(another_tool).build()
            _, kwargs = mock_init.call_args
            assert kwargs["custom_tools"] == [my_custom_tool, another_tool]
