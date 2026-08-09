"""Handle a live SDK question or confirmation request from a streaming run."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from cody.sdk import Cody


async def run(workdir: Path, auto_approve: bool) -> None:
    client = Cody().workdir(str(workdir)).interaction(enabled=True, timeout=120).build()
    async with client:
        async for chunk in client.stream(
            "检查当前目录并运行一个只读的 pwd 命令；需要确认时向我请求批准"
        ):
            if chunk.type == "text_delta":
                print(chunk.content, end="", flush=True)
            elif chunk.type == "interaction_request":
                print(f"\n[{chunk.interaction_kind}] {chunk.content}")
                if auto_approve:
                    answer = "y"
                else:
                    answer = await asyncio.to_thread(input, "Approve? [y/N] ")
                action = "approve" if answer.strip().lower() == "y" else "reject"
                await client.submit_interaction(
                    request_id=chunk.request_id,
                    action=action,
                    content=f"demo user selected {action}",
                )
            elif chunk.type == "done":
                print(f"\n[done] run_id={chunk.run_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, default=Path.cwd())
    parser.add_argument("--auto-approve", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.workdir.resolve(), args.auto_approve))


if __name__ == "__main__":
    main()
