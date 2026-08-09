"""Contract tests for the opt-in real-provider capability verifier."""

from cody.core.tools.registry import list_tool_names
from scripts.verify_live_capabilities import (
    CASES,
    LIVE_SURFACE_COVERAGE,
    LIVE_TOOL_COVERAGE,
)


def test_live_verifier_covers_every_builtin_tool():
    """A newly registered tool must name a real-provider verification case."""
    assert set(LIVE_TOOL_COVERAGE) == set(list_tool_names(include_mcp=True))
    assert set(LIVE_TOOL_COVERAGE.values()) <= set(CASES)


def test_live_verifier_covers_every_product_surface():
    expected = {
        "async_sdk",
        "sync_sdk",
        "cli",
        "tui",
        "web_rest",
        "web_sse",
        "web_websocket",
        "web_runtime",
        "approval_resume",
        "quality_repair",
        "multi_agent",
        "sandbox",
        "mcp_stdio",
        "mcp_http",
        "lsp",
        "security",
    }
    assert set(LIVE_SURFACE_COVERAGE) == expected
    assert set(LIVE_SURFACE_COVERAGE.values()) <= set(CASES)
