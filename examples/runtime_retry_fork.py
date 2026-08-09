"""Retry a failed Run and fork a completed Run from a historical checkpoint."""

from __future__ import annotations

import asyncio
from tempfile import TemporaryDirectory

from cody.core.runtime import CodyRuntime, RuntimeStoreBundle, Workflow, WorkflowNodeType

from ._support import UnusedRunner


async def retry_demo(root: str) -> None:
    workflow = (
        Workflow("retry-demo", workflow_id="demo_retry_workflow")
        .node("work", WorkflowNodeType.FUNCTION)
        .compile()
    )

    def fail(_state, _node):
        raise RuntimeError("simulated transient failure")

    first = CodyRuntime(
        UnusedRunner(),
        stores=RuntimeStoreBundle.sqlite(root),
        node_handlers={"function": fail},
        poll_interval=0,
    )
    failed = await first.start(workflow, run_id="demo_retry")
    try:
        await failed.result()
    except RuntimeError as exc:
        print("first attempt:", exc)
    await first.close()

    second = CodyRuntime(
        UnusedRunner(),
        stores=RuntimeStoreBundle.sqlite(root),
        node_handlers={"function": lambda _state, _node: {"recovered": True}},
        poll_interval=0,
    )
    try:
        retried = await second.retry(failed.run_id)
        result = await retried.result()
        print("retry status:", result.run.status.value)
    finally:
        await second.close()


async def fork_demo(root: str) -> None:
    workflow = (
        Workflow("fork-demo", workflow_id="demo_fork_workflow")
        .node("diagnose", WorkflowNodeType.FUNCTION)
        .node("implement", WorkflowNodeType.FUNCTION)
        .edge("diagnose", "implement")
        .compile()
    )
    first = CodyRuntime(
        UnusedRunner(),
        stores=RuntimeStoreBundle.sqlite(root),
        node_handlers={"function": lambda _state, node: {node.node_id: "original"}},
        poll_interval=0,
    )
    source = await first.start(workflow, run_id="demo_fork_source")
    await source.result()
    checkpoint = next(
        item
        for item in first.stores.checkpoint_store.list_checkpoints(source.run_id)
        if item.step_id == "scheduler_batch_000001"
    )
    await first.close()

    second = CodyRuntime(
        UnusedRunner(),
        stores=RuntimeStoreBundle.sqlite(root),
        node_handlers={"function": lambda _state, node: {node.node_id: "forked"}},
        poll_interval=0,
    )
    try:
        forked = await second.fork(
            checkpoint.checkpoint_id,
            new_run_id="demo_fork_child",
            metadata={"reason": "alternate implementation"},
        )
        result = await forked.result()
        print("fork parent:", result.run.parent_run_id)
        print("fork state:", result.state.data)
    finally:
        await second.close()


async def run() -> None:
    with TemporaryDirectory(prefix="cody-retry-fork-demo-") as temporary:
        await retry_demo(f"{temporary}/retry")
        await fork_demo(f"{temporary}/fork")


if __name__ == "__main__":
    asyncio.run(run())
