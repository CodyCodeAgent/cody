"""Stream rendering for CLI output."""

import asyncio
import time
from typing import AsyncIterator, Optional

from rich.markup import escape as rich_escape

from ..sdk.types import StreamChunk
from .utils import console
from ..shared import (
    SPINNER_FRAMES as _SPINNER_FRAMES,
    truncate_repr as _truncate_repr,
    format_elapsed as _format_elapsed,
    compact_message,
)


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


async def _render_stream(
    stream: AsyncIterator[StreamChunk],
    *,
    verbose: bool = False,
) -> Optional[StreamChunk]:
    """Consume a StreamChunk async iterator and render to console.

    Shared by both `run` and `chat` commands.
    Returns the done StreamChunk, or None.
    """
    in_thinking = False
    thinking_buf: list[str] = []
    done_chunk: Optional[StreamChunk] = None
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

    try:
        async for chunk in stream:
            # Stop the initial "Thinking..." spinner on first real event
            if not got_first_event and chunk.type != "compact":
                got_first_event = True
                await _stop_spinner()

            if chunk.type == "compact":
                console.print(
                    f"  [yellow]{compact_message(chunk.original_messages, chunk.compacted_messages, chunk.estimated_tokens_saved)}[/yellow]"
                )
            elif chunk.type == "thinking":
                in_thinking = True
                thinking_buf.append(chunk.content)
            elif chunk.type == "tool_call":
                await _stop_spinner()
                if in_thinking:
                    console.print(rich_escape("".join(thinking_buf)), style="dim")
                    thinking_buf.clear()
                    in_thinking = False
                args = chunk.args or {}
                args_str = ", ".join(
                    f"{k}={_truncate_repr(v)}" for k, v in list(args.items())[:3]
                )
                tool_name = chunk.tool_name or ""
                console.print(f"  [dim]→ {rich_escape(tool_name)}({rich_escape(args_str)})[/dim]")
                spinner_task = asyncio.create_task(
                    _status_spinner(
                        f"{tool_name} running...",
                        time.monotonic(),
                        done_label=f"{tool_name} done",
                    )
                )
            elif chunk.type == "tool_result":
                await _stop_spinner()
                if verbose:
                    preview = chunk.content[:200]
                    console.print(f"    [dim]{rich_escape(preview)}[/dim]")
            elif chunk.type == "text_delta":
                await _stop_spinner()
                if in_thinking:
                    console.print(rich_escape("".join(thinking_buf)), style="dim")
                    thinking_buf.clear()
                    in_thinking = False
                console.print(chunk.content, end="")
            elif chunk.type == "done":
                await _stop_spinner()
                if in_thinking:
                    console.print(rich_escape("".join(thinking_buf)), style="dim")
                    thinking_buf.clear()
                done_chunk = chunk
    finally:
        await _stop_spinner()

    # Print total elapsed time
    total = time.monotonic() - stream_start
    console.print()
    console.print(f"  [dim]Completed in {_format_elapsed(total)}[/dim]")
    return done_chunk
