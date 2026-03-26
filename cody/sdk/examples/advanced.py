"""Advanced SDK features examples.

Shows how to:
- Use stateless mode (no persistence)
- Configure circuit breaker for resource limits
- Handle human-in-the-loop interaction
- Cancel a running stream
- Inject custom storage implementations
"""

import asyncio

from cody.sdk import Cody


# ── Example 1: Stateless mode ─────────────────────────────────────────────


async def stateless_example():
    """Run without any persistence — no session, audit, or memory storage.

    Useful for one-shot scripts, CI/CD pipelines, or testing where you
    don't need to persist anything to disk.
    """
    client = (
        Cody()
        .workdir(".")
        .stateless()
        .build()
    )

    async with client:
        result = await client.run("What Python files are in this directory?")
        print(result.output)
        # No sessions.db, audit.db, or memory files created


# ── Example 2: Circuit breaker ────────────────────────────────────────────


async def circuit_breaker_example():
    """Configure circuit breaker to limit resource consumption.

    The circuit breaker automatically terminates runs that exceed
    token, cost, or step limits, or that enter infinite loops.
    """
    from cody.core.errors import CircuitBreakerError

    # Method A: keyword arguments
    client = (
        Cody()
        .workdir(".")
        .circuit_breaker(
            max_tokens=100_000,    # Stop after 100k tokens
            max_cost_usd=2.0,     # Stop after $2.00
            max_steps=30,         # Stop after 30 tool calls
        )
        .build()
    )

    async with client:
        # run() raises CircuitBreakerError when limits are hit
        try:
            result = await client.run("Refactor the entire project")
            print(result.output)
        except CircuitBreakerError as e:
            print(f"Circuit breaker triggered: {e.reason}")
            print(f"  Tokens used: {e.tokens_used}")
            print(f"  Cost: ${e.cost_usd:.4f}")


async def circuit_breaker_stream_example():
    """Circuit breaker with streaming — yields a chunk instead of raising."""
    client = (
        Cody()
        .workdir(".")
        .circuit_breaker(max_tokens=50_000, max_steps=20)
        .build()
    )

    async with client:
        async for chunk in client.stream("Analyze all files in this project"):
            if chunk.type == "text_delta":
                print(chunk.content, end="", flush=True)
            elif chunk.type == "circuit_breaker":
                print(f"\n\n[Circuit breaker: {chunk.content}]")
                break
            elif chunk.type == "done":
                print("\n\nDone!")


# ── Example 3: Human-in-the-loop interaction ──────────────────────────────


async def interaction_example():
    """Enable human-in-the-loop — the agent pauses for user confirmation.

    When enabled, dangerous tools (exec_command, write_file, etc.)
    and the question tool will pause and wait for human response.
    """
    from cody.core.errors import InteractionTimeoutError

    client = (
        Cody()
        .workdir(".")
        .interaction(enabled=True, timeout=30)
        .build()
    )

    async with client:
        try:
            async for chunk in client.stream("Refactor the main module"):
                if chunk.type == "interaction_request":
                    # The agent is waiting for your response
                    print(f"\n[{chunk.interaction_kind}] {chunk.content}")
                    if chunk.options:
                        print(f"  Options: {chunk.options}")

                    # In a real app, you'd get input from the user.
                    # Here we auto-approve for demonstration:
                    await client.submit_interaction(
                        request_id=chunk.request_id,
                        action="approve",
                        content="",
                    )
                elif chunk.type == "text_delta":
                    print(chunk.content, end="", flush=True)
                elif chunk.type == "done":
                    print("\n\nDone!")
        except InteractionTimeoutError:
            print("\nInteraction timed out — run terminated")


# ── Example 4: Cancel a running stream ────────────────────────────────────


async def cancel_stream_example():
    """Cancel a stream mid-execution using an asyncio.Event.

    Useful for implementing user-initiated stop buttons or
    cutting off after receiving enough output.
    """
    client = Cody().workdir(".").build()
    cancel = asyncio.Event()
    collected = []

    async with client:
        async for chunk in client.stream(
            "Write a detailed guide on Python async programming",
            cancel_event=cancel,
        ):
            if chunk.type == "text_delta":
                collected.append(chunk.content)
                print(chunk.content, end="", flush=True)

                # Cancel after collecting 500 characters
                if sum(len(c) for c in collected) > 500:
                    print("\n\n[Cancelling...]")
                    cancel.set()

            elif chunk.type == "cancelled":
                print("[Stream cancelled]")
                break

            elif chunk.type == "done":
                print("\n\nDone!")


# ── Example 5: Custom storage injection ───────────────────────────────────


async def custom_storage_example():
    """Inject custom storage implementations.

    You can replace the default SQLite-based storage with your own
    implementations (PostgreSQL, DynamoDB, etc.) as long as they
    satisfy the corresponding Protocol interfaces.
    """
    from cody.core.storage import NullAuditLogger

    # Use stateless as a base, but add back a real audit logger
    client = (
        Cody()
        .workdir(".")
        .stateless()                         # No persistence by default
        .audit_logger(NullAuditLogger())     # Override: use a specific logger
        .build()
    )

    async with client:
        result = await client.run("What files are here?")
        print(result.output)


if __name__ == "__main__":
    asyncio.run(stateless_example())
