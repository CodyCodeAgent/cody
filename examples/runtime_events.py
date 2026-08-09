"""Run a canonical Runtime task and inspect events, metrics, and Artifacts offline."""

from __future__ import annotations

import asyncio

from cody.core.runtime import CodyRuntime, RuntimeStoreBundle

from ._support import StaticRunner


async def run() -> None:
    stores = RuntimeStoreBundle.in_memory()
    runtime = CodyRuntime(
        StaticRunner("analysis complete"),
        stores=stores,
        poll_interval=0,
    )
    try:
        handle = await runtime.start(
            "inspect the repository",
            run_id="demo_runtime_events",
        )
        events = [event async for event in handle.events()]
        result = await handle.result()
        metrics = stores.interface().get_metrics(handle.run_id).data["metrics"]
        artifacts = stores.artifact_store.list(run_id=handle.run_id)

        print("status:", result.run.status.value)
        print("output:", result.output)
        print("events:", [event.event_type.value for event in events])
        print("artifacts:", [artifact.artifact_id for artifact in artifacts])
        print("metrics:", metrics)
    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(run())
