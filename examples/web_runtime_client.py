"""Start a canonical Run through Web API, poll it, then print its timeline."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import httpx


TERMINAL = {"completed", "failed", "cancelled", "waiting", "paused"}


async def run(base_url: str, workdir: Path, prompt: str) -> None:
    api_key = os.environ.get("CODY_AUTH_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=30) as client:
        health = await client.get("/health")
        health.raise_for_status()
        print("health:", health.json())

        started = await client.post(
            "/runtime/runs",
            json={"prompt": prompt, "workdir": str(workdir), "max_steps": 50},
        )
        started.raise_for_status()
        run_id = started.json()["run_id"]
        print("run_id:", run_id)

        while True:
            response = await client.get(
                f"/runtime/runs/{run_id}",
                params={"workdir": str(workdir)},
            )
            response.raise_for_status()
            status = response.json()["run"]["status"]
            print("status:", status)
            if status in TERMINAL:
                break
            await asyncio.sleep(0.5)

        timeline = await client.get(
            f"/runtime/runs/{run_id}/timeline",
            params={"workdir": str(workdir)},
        )
        timeline.raise_for_status()
        print("timeline items:", len(timeline.json()["items"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--workdir", type=Path, default=Path.cwd())
    parser.add_argument("prompt", nargs="?", default="总结仓库结构，不修改文件")
    args = parser.parse_args()
    asyncio.run(run(args.base_url, args.workdir.resolve(), args.prompt))


if __name__ == "__main__":
    main()
