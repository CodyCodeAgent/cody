"""Call deterministic built-in tools directly without invoking a model."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from cody import AsyncCodyClient


async def run(workdir: Path) -> None:
    async with AsyncCodyClient(workdir=str(workdir)) as client:
        readme = await client.read_file("README.md")
        python_files = await client.glob("**/*.py")
        matches = await client.grep("class CodyRuntime", include="*.py")
        print(f"README characters: {len(readme)}")
        print(f"Python files (preview):\n{python_files[:500]}")
        print(f"CodyRuntime definitions:\n{matches}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, default=Path.cwd())
    args = parser.parse_args()
    asyncio.run(run(args.workdir.resolve()))


if __name__ == "__main__":
    main()
