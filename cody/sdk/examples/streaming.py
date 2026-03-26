"""Streaming example for Cody SDK.

Shows how to consume streamed responses in real-time.
"""

import asyncio

from cody.sdk import AsyncCodyClient


async def stream_example():
    """Stream a response token by token."""
    async with AsyncCodyClient(workdir=".") as client:
        print("Cody: ", end="", flush=True)

        async for chunk in client.stream("Explain what Python decorators are"):
            if chunk.type == "text_delta":
                print(chunk.content, end="", flush=True)
            elif chunk.type == "tool_call":
                print(f"\n  [tool: {chunk.tool_name}({chunk.args})]", flush=True)
            elif chunk.type == "tool_result":
                print(f"\n  [result: {chunk.content[:80]}]", flush=True)
            elif chunk.type == "thinking":
                pass  # Optionally show thinking
            elif chunk.type == "done":
                print(f"\n\nDone! (tokens: {chunk.usage.total_tokens})")


if __name__ == "__main__":
    asyncio.run(stream_example())
