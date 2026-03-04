"""Event hooks example for Cody SDK.

Shows how to monitor SDK operations with event handlers.
"""

import asyncio

from cody.sdk import Cody, EventType, ToolEvent, RunEvent


async def events_example():
    """Use event hooks to monitor tool calls and run lifecycle."""
    client = (
        Cody()
        .workdir(".")
        .enable_events()
        .enable_metrics()
        .build()
    )

    # Register event handlers
    client.on(EventType.TOOL_CALL, on_tool_call)
    client.on(EventType.TOOL_RESULT, on_tool_result)
    client.on(EventType.RUN_START, on_run_start)
    client.on(EventType.RUN_END, on_run_end)

    async with client:
        await client.run("Read the README.md file and summarize it")

        # Print collected metrics
        metrics = client.get_metrics()
        if metrics:
            print("\nMetrics:")
            print(f"  Total runs: {metrics['total_runs']}")
            print(f"  Total tokens: {metrics['total_tokens']}")
            print(f"  Tool calls: {metrics['total_tool_calls']}")


def on_tool_call(event: ToolEvent):
    print(f"  -> Calling tool: {event.tool_name}")


def on_tool_result(event: ToolEvent):
    result_preview = event.result[:80] if event.result else ""
    print(f"  <- Tool {event.tool_name} done ({event.duration:.2f}s): {result_preview}...")


def on_run_start(event: RunEvent):
    print(f"Run started: {event.prompt[:60]}...")


def on_run_end(event: RunEvent):
    result_preview = event.result[:80] if event.result else ""
    print(f"Run completed: {result_preview}...")


if __name__ == "__main__":
    asyncio.run(events_example())
