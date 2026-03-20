"""User input queue for proactive (unsolicited) human input during agent runs.

This allows users to send messages to a running agent without waiting for
the AI to ask first. Messages are queued and injected at the next node
boundary via CallToolsNode.user_prompt.
"""

import asyncio


class UserInputQueue:
    """Thread-safe async queue for user-initiated messages."""

    def __init__(self):
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    async def put(self, message: str) -> None:
        """Enqueue a user message."""
        await self._queue.put(message)

    def try_get(self) -> str | None:
        """Non-blocking get. Returns None if empty."""
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def drain_all(self) -> list[str]:
        """Non-blocking drain: return all queued messages."""
        messages = []
        while True:
            try:
                messages.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return messages
