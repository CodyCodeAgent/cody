"""Tests for CLI stream rendering with StreamChunk."""

import pytest
from unittest.mock import patch

from cody.sdk.types import StreamChunk, Usage
from cody.cli.rendering import _render_stream


async def _chunks(*items):
    """Create an async iterator from StreamChunk objects."""
    for item in items:
        yield item


# ── _render_stream basic event types ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_render_stream_text_delta():
    """text_delta chunks should be printed to console."""
    stream = _chunks(
        StreamChunk(type="text_delta", content="Hello "),
        StreamChunk(type="text_delta", content="world"),
        StreamChunk(type="done", content="Hello world", usage=Usage(total_tokens=10)),
    )
    with patch("cody.cli.rendering.console") as mock_console:
        result = await _render_stream(stream)

    assert result is not None
    assert result.type == "done"
    assert result.content == "Hello world"
    # text_delta prints with end=""
    text_calls = [
        c for c in mock_console.print.call_args_list
        if c.kwargs.get("end") == ""
    ]
    assert len(text_calls) == 2


@pytest.mark.asyncio
async def test_render_stream_tool_call():
    """tool_call chunks should show tool name and args."""
    stream = _chunks(
        StreamChunk(
            type="tool_call", tool_name="read_file",
            args={"path": "test.py"}, tool_call_id="tc_1",
        ),
        StreamChunk(
            type="tool_result", content="file contents",
            tool_name="read_file", tool_call_id="tc_1",
        ),
        StreamChunk(type="done", content="done"),
    )
    with patch("cody.cli.rendering.console") as mock_console:
        result = await _render_stream(stream)

    assert result is not None
    # Check that tool name appears in output
    printed = " ".join(str(c) for c in mock_console.print.call_args_list)
    assert "read_file" in printed


@pytest.mark.asyncio
async def test_render_stream_tool_result_verbose():
    """tool_result preview shown only with verbose=True."""
    stream = _chunks(
        StreamChunk(
            type="tool_result", content="some long result text",
            tool_name="grep", tool_call_id="tc_2",
        ),
        StreamChunk(type="done", content="done"),
    )
    with patch("cody.cli.rendering.console") as mock_console:
        await _render_stream(stream, verbose=True)

    # With verbose, tool result preview should appear
    printed = " ".join(str(c) for c in mock_console.print.call_args_list)
    assert "some long result" in printed


@pytest.mark.asyncio
async def test_render_stream_tool_result_not_verbose():
    """tool_result preview NOT shown with verbose=False (default)."""
    stream = _chunks(
        StreamChunk(
            type="tool_result", content="some long result text",
            tool_name="grep", tool_call_id="tc_2",
        ),
        StreamChunk(type="done", content="done"),
    )
    with patch("cody.cli.rendering.console") as mock_console:
        await _render_stream(stream, verbose=False)

    # Without verbose, tool result content should NOT appear
    printed = " ".join(str(c) for c in mock_console.print.call_args_list)
    assert "some long result" not in printed


@pytest.mark.asyncio
async def test_render_stream_compact():
    """compact chunks should show compression message."""
    stream = _chunks(
        StreamChunk(
            type="compact",
            original_messages=20, compacted_messages=5,
            estimated_tokens_saved=8000,
        ),
        StreamChunk(type="done", content="done"),
    )
    with patch("cody.cli.rendering.console") as mock_console:
        await _render_stream(stream)

    printed = " ".join(str(c) for c in mock_console.print.call_args_list)
    assert "20" in printed or "compact" in printed.lower()


@pytest.mark.asyncio
async def test_render_stream_thinking():
    """thinking chunks should be buffered and rendered dim."""
    stream = _chunks(
        StreamChunk(type="thinking", content="Let me "),
        StreamChunk(type="thinking", content="think..."),
        StreamChunk(type="text_delta", content="Answer"),
        StreamChunk(type="done", content="Answer"),
    )
    with patch("cody.cli.rendering.console") as mock_console:
        await _render_stream(stream)

    # Thinking should be rendered with style="dim"
    dim_calls = [
        c for c in mock_console.print.call_args_list
        if c.kwargs.get("style") == "dim"
    ]
    assert len(dim_calls) >= 1


@pytest.mark.asyncio
async def test_render_stream_returns_done_chunk():
    """_render_stream should return the done StreamChunk."""
    usage = Usage(input_tokens=100, output_tokens=50, total_tokens=150)
    stream = _chunks(
        StreamChunk(type="text_delta", content="hi"),
        StreamChunk(
            type="done", content="hi", usage=usage,
            message_history=[{"role": "assistant"}],
        ),
    )
    with patch("cody.cli.rendering.console"):
        result = await _render_stream(stream)

    assert result is not None
    assert result.type == "done"
    assert result.usage.total_tokens == 150
    assert result.message_history == [{"role": "assistant"}]


@pytest.mark.asyncio
async def test_render_stream_empty():
    """_render_stream returns None if no done chunk received."""
    stream = _chunks()  # empty stream
    with patch("cody.cli.rendering.console"):
        result = await _render_stream(stream)

    assert result is None
