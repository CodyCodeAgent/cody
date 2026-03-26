"""Tests for per-run tool selection (#9)."""

from unittest.mock import MagicMock

from cody.core.tools.registry import (
    CORE_TOOLS,
    register_tools,
    list_tool_names,
    _should_include,
)


# ── _should_include helper ───────────────────────────────────────────────────


class TestShouldInclude:
    def _func(self, name: str):
        f = lambda: None  # noqa: E731
        f.__name__ = name
        return f

    def test_no_filter(self):
        assert _should_include(self._func("read_file"), None, None) is True

    def test_include_match(self):
        assert _should_include(self._func("grep"), {"grep", "glob"}, None) is True

    def test_include_no_match(self):
        assert _should_include(self._func("exec_command"), {"grep"}, None) is False

    def test_exclude_match(self):
        assert _should_include(self._func("exec_command"), None, {"exec_command"}) is False

    def test_exclude_no_match(self):
        assert _should_include(self._func("read_file"), None, {"exec_command"}) is True

    def test_include_takes_precedence(self):
        """When both are set, include_tools is checked first."""
        assert _should_include(self._func("grep"), {"grep"}, {"grep"}) is True


# ── register_tools with filters ──────────────────────────────────────────────


class TestRegisterToolsFiltered:
    def test_include_tools(self):
        agent = MagicMock()
        agent.tool.return_value = lambda f: f
        register_tools(agent, include_tools=["read_file", "grep"])
        # Only 2 tools should be registered
        assert agent.tool.call_count == 2

    def test_exclude_tools(self):
        agent = MagicMock()
        agent.tool.return_value = lambda f: f
        register_tools(agent, exclude_tools=["exec_command"])
        expected = len(CORE_TOOLS) - 1
        assert agent.tool.call_count == expected

    def test_include_empty_list(self):
        """Empty include list = nothing registered."""
        agent = MagicMock()
        agent.tool.return_value = lambda f: f
        register_tools(agent, include_tools=[])
        assert agent.tool.call_count == 0

    def test_exclude_empty_list(self):
        """Empty exclude list = all registered."""
        agent = MagicMock()
        agent.tool.return_value = lambda f: f
        register_tools(agent, exclude_tools=[])
        assert agent.tool.call_count == len(CORE_TOOLS)

    def test_include_with_custom_tools(self):
        """Custom tools are also filtered by include_tools."""
        async def my_tool(ctx, query: str) -> str:
            return query

        agent = MagicMock()
        agent.tool.return_value = lambda f: f
        register_tools(
            agent,
            custom_tools=[my_tool],
            include_tools=["read_file", "my_tool"],
        )
        assert agent.tool.call_count == 2  # read_file + my_tool

    def test_exclude_custom_tools(self):
        """Custom tools can be excluded by name."""
        async def my_tool(ctx, query: str) -> str:
            return query

        agent = MagicMock()
        agent.tool.return_value = lambda f: f
        register_tools(
            agent,
            custom_tools=[my_tool],
            exclude_tools=["my_tool"],
        )
        assert agent.tool.call_count == len(CORE_TOOLS)  # all core, no custom


# ── list_tool_names ──────────────────────────────────────────────────────────


class TestListToolNames:
    def test_core_tools(self):
        names = list_tool_names()
        assert "read_file" in names
        assert "grep" in names
        assert "exec_command" in names
        assert len(names) == len(CORE_TOOLS)

    def test_with_mcp(self):
        names = list_tool_names(include_mcp=True)
        assert "mcp_call" in names
        assert len(names) > len(CORE_TOOLS)
