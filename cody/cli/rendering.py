"""Stream rendering for CLI output."""

import asyncio
import time
from typing import Optional

from rich.markup import escape as rich_escape

from ..core.runner import (
    CodyResult, CompactEvent, ThinkingEvent, TextDeltaEvent,
    ToolCallEvent, ToolResultEvent, DoneEvent,
)
from .utils import console, _truncate_repr, _format_elapsed, _SPINNER_FRAMES


async def _status_spinner(label: str, start: float, *, done_label: str = "") -> None:
    """Show an animated spinner with a label and elapsed time.

    If *done_label* is set, print it on completion; otherwise just clear the line.
    """
    import sys

    i = 0
    try:
        while True:
            elapsed = time.monotonic() - start
            frame = _SPINNER_FRAMES[i % len(_SPINNER_FRAMES)]
            sys.stdout.write(
                f"\r    {frame} {label} ({_format_elapsed(elapsed)})"
            )
            sys.stdout.flush()
            i += 1
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        elapsed = time.monotonic() - start
        if done_label:
            sys.stdout.write(
                f"\r    ✓ {done_label} ({_format_elapsed(elapsed)})\n"
            )
        else:
            sys.stdout.write("\r" + " " * 60 + "\r")
        sys.stdout.flush()


async def _render_stream(stream, *, verbose: bool = False) -> "Optional[CodyResult]":
    """Consume a StreamEvent async generator and render to console.

    Shared by both `run` and `chat` commands.
    Returns the CodyResult from the DoneEvent, or None.
    """
    in_thinking = False
    thinking_buf = []
    result = None
    spinner_task: Optional[asyncio.Task] = None
    stream_start = time.monotonic()
    got_first_event = False

    async def _stop_spinner():
        nonlocal spinner_task
        if spinner_task and not spinner_task.done():
            spinner_task.cancel()
            try:
                await spinner_task
            except asyncio.CancelledError:
                pass
        spinner_task = None

    # Show "Thinking..." spinner while waiting for first response
    spinner_task = asyncio.create_task(
        _status_spinner("Thinking...", stream_start)
    )

    async for event in stream:
        # Stop the initial "Thinking..." spinner on first real event
        if not got_first_event and not isinstance(event, CompactEvent):
            got_first_event = True
            await _stop_spinner()

        if isinstance(event, CompactEvent):
            console.print(
                f"  [yellow]⚡ 上下文已压缩：{event.original_messages} → "
                f"{event.compacted_messages} 条消息，"
                f"节省约 ~{event.estimated_tokens_saved} tokens[/yellow]"
            )
        elif isinstance(event, ThinkingEvent):
            in_thinking = True
            thinking_buf.append(event.content)
        elif isinstance(event, ToolCallEvent):
            await _stop_spinner()
            if in_thinking:
                console.print(rich_escape("".join(thinking_buf)), style="dim")
                thinking_buf.clear()
                in_thinking = False
            args_str = ", ".join(
                f"{k}={_truncate_repr(v)}" for k, v in list(event.args.items())[:3]
            )
            console.print(f"  [dim]→ {rich_escape(event.tool_name)}({rich_escape(args_str)})[/dim]")
            spinner_task = asyncio.create_task(
                _status_spinner(
                    f"{event.tool_name} running...",
                    time.monotonic(),
                    done_label=f"{event.tool_name} done",
                )
            )
        elif isinstance(event, ToolResultEvent):
            await _stop_spinner()
            if verbose:
                preview = event.result[:200]
                console.print(f"    [dim]{rich_escape(preview)}[/dim]")
        elif isinstance(event, TextDeltaEvent):
            await _stop_spinner()
            if in_thinking:
                console.print(rich_escape("".join(thinking_buf)), style="dim")
                thinking_buf.clear()
                in_thinking = False
            console.print(event.content, end="")
        elif isinstance(event, DoneEvent):
            await _stop_spinner()
            if in_thinking:
                console.print(rich_escape("".join(thinking_buf)), style="dim")
                thinking_buf.clear()
            result = event.result

    # Print total elapsed time
    total = time.monotonic() - stream_start
    console.print()
    console.print(f"  [dim]Completed in {_format_elapsed(total)}[/dim]")
    return result
