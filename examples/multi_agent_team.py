"""Route a dependency DAG across deterministic specialist Agent backends."""

from __future__ import annotations

import asyncio

from cody.core.runtime import (
    AgentRole,
    AgentTask,
    AsyncMultiAgentCoordinator,
    InMemoryArtifactStore,
    WorkflowState,
)


async def run() -> None:
    artifacts = InMemoryArtifactStore()
    coordinator = AsyncMultiAgentCoordinator(
        max_concurrency=2,
        artifact_store=artifacts,
    )

    async def researcher(task, _state):
        await asyncio.sleep(0.05)
        return {"risk": "authentication path lacks a regression test", "task": task.task_id}

    async def engineer(task, _state):
        await asyncio.sleep(0.05)
        return {"patch": "add regression coverage", "task": task.task_id}

    async def reviewer(_task, state):
        inputs = sorted((state.data.get("agent_outputs") or {}).keys())
        return {"decision": "approved", "inputs": inputs}

    coordinator.register_agent(
        AgentRole("researcher", capabilities=frozenset({"diagnosis"})),
        researcher,
    )
    coordinator.register_agent(
        AgentRole("engineer", capabilities=frozenset({"implementation"})),
        engineer,
    )
    coordinator.register_agent(
        AgentRole("reviewer", capabilities=frozenset({"review"})),
        reviewer,
    )

    tasks = [
        AgentTask.create(
            "diagnose the failure",
            task_id="diagnose",
            required_capabilities={"diagnosis"},
        ),
        AgentTask.create(
            "prepare a patch",
            task_id="implement",
            required_capabilities={"implementation"},
        ),
        AgentTask.create(
            "review the combined result",
            task_id="review",
            required_capabilities={"review"},
            depends_on=("diagnose", "implement"),
        ),
    ]
    state, records = await coordinator.run(
        tasks,
        state=WorkflowState(workflow_id="demo_team", run_id="demo_multi_agent"),
    )
    print(
        "assignments:",
        {record.task.task_id: record.assigned_agent_id for record in records},
    )
    print("outputs:", state.data["agent_outputs"])
    print("artifact_count:", len(artifacts.list(run_id="demo_multi_agent")))


if __name__ == "__main__":
    asyncio.run(run())
