"""Expose a business lookup function as a model-callable Tool with a hook."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from pydantic_ai import RunContext

from cody.core.deps import CodyDeps
from cody.sdk import Cody


async def lookup_service_owner(_ctx: RunContext[CodyDeps], service: str) -> str:
    """Return the owning team and runbook for an internal service."""
    catalog = {
        "payments": "team=money-platform; runbook=runbooks/payments.md",
        "search": "team=discovery; runbook=runbooks/search.md",
    }
    return catalog.get(service.lower(), f"service={service}; owner=unknown")


async def log_tool_call(tool_name: str, args: dict) -> dict:
    print(f"[before_tool] {tool_name} args={args}")
    return args


async def run(workdir: Path, service: str) -> None:
    client = (
        Cody()
        .workdir(str(workdir))
        .tool(lookup_service_owner)
        .before_tool(log_tool_call)
        .build()
    )
    async with client:
        result = await client.run(
            f"查询 {service} 的负责人和 runbook。必须使用 lookup_service_owner。",
            include_tools=["lookup_service_owner"],
        )
        print(result.output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", nargs="?", default="payments")
    parser.add_argument("--workdir", type=Path, default=Path.cwd())
    args = parser.parse_args()
    asyncio.run(run(args.workdir.resolve(), args.service))


if __name__ == "__main__":
    main()
