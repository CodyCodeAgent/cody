"""Run a model-backed code review with an explicitly read-only tool surface."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from cody import AsyncCodyClient


READ_ONLY_TOOLS = ["read_file", "grep", "glob", "list_directory", "search_files"]


async def run(workdir: Path, target: str) -> None:
    prompt = (
        f"审查 {target}，只报告有明确证据的问题。"
        "按严重程度、文件位置、影响和建议修复方式输出；不要修改文件。"
    )
    async with AsyncCodyClient(workdir=str(workdir)) as client:
        result = await client.run(prompt, include_tools=READ_ONLY_TOOLS)
        print(result.output)
        print(f"\nrun_id={result.run_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", default="cody/core/runtime")
    parser.add_argument("--workdir", type=Path, default=Path.cwd())
    args = parser.parse_args()
    asyncio.run(run(args.workdir.resolve(), args.target))


if __name__ == "__main__":
    main()
