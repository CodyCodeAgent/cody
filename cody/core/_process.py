"""Shared async subprocess helpers."""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def cancel_task_silently(task: Optional[asyncio.Task]) -> None:
    """Cancel an asyncio task and suppress CancelledError."""
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def terminate_process(
    process: Optional[asyncio.subprocess.Process],
    timeout: float = 5.0,
) -> None:
    """Terminate a subprocess gracefully, escalating to kill on timeout.

    1. Send SIGTERM
    2. Wait up to *timeout* seconds
    3. If still alive, send SIGKILL and wait
    """
    if process is None or process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
