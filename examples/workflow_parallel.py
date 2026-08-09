"""Execute two independent Workflow branches concurrently, then join them."""

from __future__ import annotations

import asyncio

from cody.core.runtime import (
    AsyncWorkflowScheduler,
    Workflow,
    WorkflowEdgeType,
    WorkflowNodeType,
)


def build_workflow():
    return (
        Workflow("parallel-demo", workflow_id="demo_parallel_workflow")
        .node("start", WorkflowNodeType.FUNCTION)
        .node("tests", WorkflowNodeType.FUNCTION)
        .node("security", WorkflowNodeType.FUNCTION)
        .node("report", WorkflowNodeType.FUNCTION)
        .edge("start", "tests", edge_type=WorkflowEdgeType.PARALLEL)
        .edge("start", "security", edge_type=WorkflowEdgeType.PARALLEL)
        .edge("tests", "report", edge_type=WorkflowEdgeType.JOIN)
        .edge("security", "report", edge_type=WorkflowEdgeType.JOIN)
        .compile()
    )


async def run() -> None:
    branches_started: set[str] = set()
    both_started = asyncio.Event()

    async def handler(state, node):
        if node.node_id in {"tests", "security"}:
            branches_started.add(node.node_id)
            if len(branches_started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=1)
            return {node.node_id: {"passed": True}}
        if node.node_id == "report":
            return {
                "report": {
                    "tests": state.data["tests"],
                    "security": state.data["security"],
                }
            }
        return {"started": True}

    scheduler = AsyncWorkflowScheduler(
        node_handlers={"function": handler},
        max_concurrency=2,
    )
    state = await scheduler.run(build_workflow(), run_id="demo_parallel_run")
    print("completed:", state.completed_node_ids)
    print("report:", state.data["report"])


if __name__ == "__main__":
    asyncio.run(run())
