"""Write, query, and clear project-scoped memory without calling a model."""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from cody.core.memory import MemoryEntry, ProjectMemoryStore


async def run() -> None:
    with TemporaryDirectory(prefix="cody-memory-demo-") as workdir:
        root = Path(workdir)
        store = ProjectMemoryStore.from_workdir(root, base_dir=root / ".memory")
        await store.add_entries(
            "conventions",
            [
                MemoryEntry(
                    content="Public Python functions require type annotations.",
                    confidence=0.95,
                    tags=["python", "style"],
                )
            ],
        )
        await store.add_entries(
            "decisions",
            [
                MemoryEntry(
                    content="Runtime state uses PostgreSQL in production.",
                    source_task_id="architecture-review",
                )
            ],
        )
        memory = store.get_all_entries()
        print("categories:", sorted(memory))
        print("conventions:", [entry.content for entry in memory["conventions"]])
        store.clear()
        print("after clear:", store.get_all_entries())


if __name__ == "__main__":
    asyncio.run(run())
