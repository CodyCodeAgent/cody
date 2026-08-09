"""Write, query, and clear project-scoped memory without calling a model."""

from __future__ import annotations

import asyncio
from tempfile import TemporaryDirectory

from cody import AsyncCodyClient


async def run() -> None:
    with TemporaryDirectory(prefix="cody-memory-demo-") as workdir:
        async with AsyncCodyClient(workdir=workdir) as client:
            await client.add_memory(
                category="conventions",
                content="Public Python functions require type annotations.",
                confidence=0.95,
                tags=["python", "style"],
            )
            await client.add_memory(
                category="decisions",
                content="Runtime state uses PostgreSQL in production.",
                source_task_id="architecture-review",
            )
            memory = await client.get_memory()
            print("categories:", sorted(memory))
            print("conventions:", memory["conventions"])
            await client.clear_memory()
            print("after clear:", await client.get_memory())


if __name__ == "__main__":
    asyncio.run(run())
