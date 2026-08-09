"""Fail a Quality Gate once, repair state, and pass the bounded recheck."""

from __future__ import annotations

import asyncio

from cody.core.runtime import (
    ArtifactType,
    CodyRuntime,
    Workflow,
    WorkflowEdgeType,
    WorkflowNodeType,
)

from ._support import UnusedRunner


def build_workflow():
    return (
        Workflow("quality-demo", workflow_id="demo_quality_workflow")
        .node(
            "gate",
            WorkflowNodeType.QUALITY_GATE,
            metadata={
                "max_repairs": 2,
                "quality_gate": {
                    "gate_id": "tests_gate",
                    "metrics": [
                        {"metric_id": "tests", "threshold": 1.0, "required": True}
                    ],
                },
            },
        )
        .node("repair", WorkflowNodeType.FUNCTION)
        .node("deliver", WorkflowNodeType.FUNCTION)
        .edge("gate", "deliver")
        .edge(
            "gate",
            "repair",
            edge_type=WorkflowEdgeType.FALLBACK,
            metadata={"allow_revisit": True},
        )
        .edge("repair", "gate", metadata={"allow_revisit": True})
        .compile()
    )


async def run() -> None:
    evaluations: list[bool] = []

    async def tests_evaluator(state, _metric):
        passed = bool(state.data.get("fixed"))
        evaluations.append(passed)
        return passed

    async def function_handler(_state, node):
        if node.node_id == "repair":
            return {"fixed": True, "repair": "added regression test"}
        return {"delivered": True}

    runtime = CodyRuntime(
        UnusedRunner(),
        quality_evaluators={"tests": tests_evaluator},
        node_handlers={"function": function_handler},
        poll_interval=0,
    )
    try:
        handle = await runtime.start(build_workflow(), run_id="demo_quality_repair")
        result = await handle.result()
        reviews = runtime.stores.artifact_store.list(
            run_id=handle.run_id,
            artifact_type=ArtifactType.REVIEW,
        )
        print("evaluations:", evaluations)
        print("status:", result.run.status.value)
        print("quality attempts:", result.state.data["quality_gate_attempts"])
        print("review artifacts:", len(reviews))
    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(run())
