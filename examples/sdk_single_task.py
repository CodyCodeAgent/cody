"""Run one real model-backed coding task with the Python SDK."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from cody import AsyncCodyClient


async def run(prompt: str, workdir: Path) -> None:
    async with AsyncCodyClient(workdir=str(workdir)) as client:
        result = await client.run(prompt)
        print(result.output)
        print(f"\nrun_id={result.run_id} session_id={result.session_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", default="总结这个仓库的架构，不修改文件")
    parser.add_argument("--workdir", type=Path, default=Path.cwd())
    args = parser.parse_args()
    asyncio.run(run(args.prompt, args.workdir.resolve()))


if __name__ == "__main__":
    main()
