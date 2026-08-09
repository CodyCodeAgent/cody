"""Stream a real response and continue the same persistent session."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from cody import AsyncCodyClient


async def run(workdir: Path) -> None:
    async with AsyncCodyClient(workdir=str(workdir)) as client:
        session = await client.create_session(title="Streaming Demo")
        async for chunk in client.stream(
            "找出这个仓库最重要的三个模块",
            session_id=session.id,
            include_tools=["read_file", "grep", "glob", "list_directory"],
        ):
            if chunk.type == "text_delta":
                print(chunk.content, end="", flush=True)
            elif chunk.type == "tool_call":
                print(f"\n[tool] {chunk.tool_name}", flush=True)
            elif chunk.type == "done":
                print(f"\n[done] run_id={chunk.run_id}")

        follow_up = await client.run(
            "把刚才的结论整理成一份两阶段阅读计划",
            session_id=session.id,
            include_tools=[],
        )
        print(f"\nFollow-up:\n{follow_up.output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, default=Path.cwd())
    args = parser.parse_args()
    asyncio.run(run(args.workdir.resolve()))


if __name__ == "__main__":
    main()
