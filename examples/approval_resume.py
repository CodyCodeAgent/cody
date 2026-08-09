"""Persist a waiting approval and resume it with a new Runtime instance."""

from __future__ import annotations

import asyncio
from tempfile import TemporaryDirectory

from cody.core.runtime import (
    CodyRuntime,
    RuntimeStoreBundle,
    Workflow,
    WorkflowNodeType,
    WorkflowWaiting,
)

from ._support import StaticRunner


def build_workflow():
    return (
        Workflow("approval-demo", workflow_id="demo_approval_workflow")
        .node(
            "approval",
            WorkflowNodeType.HUMAN_APPROVAL,
            metadata={"request": {"action": "deploy", "environment": "staging"}},
        )
        .node("agent", WorkflowNodeType.AGENT)
        .edge("approval", "agent")
        .compile()
    )


async def run() -> None:
    with TemporaryDirectory(prefix="cody-approval-demo-") as root:
        first = CodyRuntime(
            StaticRunner("deployment plan ready", workdir=root),
            stores=RuntimeStoreBundle.sqlite(root),
            poll_interval=0,
        )
        waiting = await first.start(
            build_workflow(),
            {"task": "prepare a safe deployment"},
            run_id="demo_approval_resume",
        )
        try:
            await waiting.result()
        except WorkflowWaiting:
            print("status before approval:", waiting.record.status.value)

        approval = first.stores.approval_store.list(run_id=waiting.run_id)[0]
        first.approve(approval.approval_id, {"approved": True, "actor": "demo-user"})
        await first.close()

        second = CodyRuntime(
            StaticRunner("deployment plan ready", workdir=root),
            stores=RuntimeStoreBundle.sqlite(root),
            poll_interval=0,
        )
        try:
            resumed = await second.resume(waiting.run_id)
            result = await resumed.result()
            print("status after resume:", result.run.status.value)
            print("output:", result.output)
        finally:
            await second.close()


if __name__ == "__main__":
    asyncio.run(run())
