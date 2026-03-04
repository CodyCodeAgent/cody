"""Basic usage examples for Cody SDK.

Three ways to create a client:
1. Builder pattern (recommended)
2. Direct construction
3. Config object
"""

import asyncio

from cody.sdk import AsyncCodyClient, Cody, config


# ── Method 1: Builder pattern ───────────────────────────────────────────────


async def builder_example():
    """Create client using the builder pattern."""
    client = (
        Cody()
        .workdir(".")
        .model("anthropic:claude-sonnet-4-0")
        .thinking(True, budget=10000)
        .build()
    )

    async with client:
        result = await client.run("Create a hello.py that prints Hello World")
        print(f"Output: {result.output}")


# ── Method 2: Direct construction ────────────────────────────────────────────


async def direct_example():
    """Create client with direct parameters."""
    async with AsyncCodyClient(workdir=".") as client:
        result = await client.run("What files are in this directory?")
        print(f"Output: {result.output}")


# ── Method 3: Config object ─────────────────────────────────────────────────


async def config_example():
    """Create client with a config object."""
    cfg = config(
        model="anthropic:claude-sonnet-4-0",
        workdir=".",
        enable_thinking=True,
    )

    async with AsyncCodyClient(config=cfg) as client:
        result = await client.run("List the project structure")
        print(f"Output: {result.output}")


# ── Multi-turn session ──────────────────────────────────────────────────────


async def session_example():
    """Multi-turn conversation using sessions."""
    async with AsyncCodyClient(workdir=".") as client:
        session = await client.create_session(title="Demo session")

        r1 = await client.run("Create a Flask app", session_id=session.id)
        print(f"Step 1: {r1.output[:100]}...")

        r2 = await client.run("Add a /health endpoint", session_id=session.id)
        print(f"Step 2: {r2.output[:100]}...")


if __name__ == "__main__":
    asyncio.run(builder_example())
