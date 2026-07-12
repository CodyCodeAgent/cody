import asyncio

import pytest

from cody.core.runtime import (
    AgentRole,
    AgentTask,
    AgentTaskStatus,
    AsyncMultiAgentCoordinator,
    CodyRuntime,
    InMemoryArtifactStore,
    RunStatus,
    Workflow,
    WorkflowCancelled,
    WorkflowNodeType,
    WorkflowState,
)


@pytest.mark.asyncio
async def test_async_coordinator_runs_independent_agents_concurrently_then_dependency():
    started = set()
    gate = asyncio.Event()
    review_inputs = []

    async def backend(task, state):
        if task.task_id in {"research", "implement"}:
            started.add(task.task_id)
            if len(started) == 2:
                gate.set()
            await asyncio.wait_for(gate.wait(), timeout=0.2)
            return {task.task_id: "done"}
        review_inputs.append(dict(state.data.get("agent_outputs") or {}))
        return {"review": "approved"}

    coordinator = AsyncMultiAgentCoordinator(max_concurrency=2)
    coordinator.register_agent(
        AgentRole("worker", capabilities=frozenset({"work"})),
        backend,
    )
    tasks = [
        AgentTask.create(
            "research",
            task_id="research",
            required_capabilities={"work"},
        ),
        AgentTask.create(
            "implement",
            task_id="implement",
            required_capabilities={"work"},
        ),
        AgentTask.create(
            "review",
            task_id="review",
            required_capabilities={"work"},
            depends_on=("research", "implement"),
        ),
    ]
    state = WorkflowState(workflow_id="team", run_id="run_team")

    final_state, records = await coordinator.run(tasks, state=state)

    assert started == {"research", "implement"}
    assert review_inputs == [
        {
            "implement": {"implement": "done"},
            "research": {"research": "done"},
        }
    ]
    assert all(record.status == AgentTaskStatus.COMPLETED for record in records)
    assert final_state.data["agent_outputs"]["review"] == {"review": "approved"}


@pytest.mark.asyncio
async def test_async_coordinator_uses_fallback_agent_and_persists_artifact():
    artifact_store = InMemoryArtifactStore()
    coordinator = AsyncMultiAgentCoordinator(artifact_store=artifact_store)

    async def broken(_task, _state):
        raise RuntimeError("agent unavailable")

    async def healthy(_task, _state):
        return {"fixed": True}

    coordinator.register_agent(
        AgentRole("primary", capabilities=frozenset({"code"})),
        broken,
    )
    coordinator.register_agent(
        AgentRole("fallback", capabilities=frozenset({"code"})),
        healthy,
    )
    task = AgentTask.create(
        "fix",
        task_id="fix",
        required_capabilities={"code"},
        preferred_agent_id="primary",
        fallback_agent_ids=("fallback",),
        metadata={"max_attempts": 2},
    )

    _, records = await coordinator.run(
        [task],
        state=WorkflowState(workflow_id="team", run_id="run_fallback_agent"),
    )

    assert records[0].status == AgentTaskStatus.COMPLETED
    assert records[0].assigned_agent_id == "fallback"
    assert records[0].attempts == 2
    artifacts = artifact_store.list(run_id="run_fallback_agent")
    assert len(artifacts) == 1
    assert artifacts[0].content == {"fixed": True}


@pytest.mark.asyncio
async def test_async_coordinator_skips_dependents_after_partial_failure():
    coordinator = AsyncMultiAgentCoordinator()

    async def backend(task, _state):
        if task.task_id == "bad":
            raise RuntimeError("failed")
        return {"ok": True}

    coordinator.register_agent(AgentRole("worker"), backend)
    tasks = [
        AgentTask.create("bad", task_id="bad", metadata={"max_attempts": 1}),
        AgentTask.create("independent", task_id="independent"),
        AgentTask.create("blocked", task_id="blocked", depends_on=("bad",)),
    ]

    _, records = await coordinator.run(
        tasks,
        state=WorkflowState(workflow_id="team", run_id="run_partial"),
    )

    statuses = {record.task.task_id: record.status for record in records}
    assert statuses == {
        "bad": AgentTaskStatus.FAILED,
        "independent": AgentTaskStatus.COMPLETED,
        "blocked": AgentTaskStatus.SKIPPED,
    }


@pytest.mark.asyncio
async def test_async_coordinator_propagates_cancellation_to_active_agents():
    cancel_event = asyncio.Event()
    started = asyncio.Event()
    was_cancelled = asyncio.Event()

    async def backend(_task, _state):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            was_cancelled.set()
            raise

    coordinator = AsyncMultiAgentCoordinator(cancel_event=cancel_event)
    coordinator.register_agent(AgentRole("worker"), backend)
    execution = asyncio.create_task(
        coordinator.run(
            [AgentTask.create("work", task_id="work")],
            state=WorkflowState(workflow_id="team", run_id="run_cancel_team"),
        )
    )
    await asyncio.wait_for(started.wait(), timeout=0.2)
    cancel_event.set()

    with pytest.raises(WorkflowCancelled):
        await asyncio.wait_for(execution, timeout=0.2)
    assert was_cancelled.is_set()


@pytest.mark.asyncio
async def test_cody_runtime_executes_declarative_agent_team_node():
    class UnusedRunner:
        pass

    coordinator = AsyncMultiAgentCoordinator(max_concurrency=2)

    async def backend(task, _state):
        await asyncio.sleep(0)
        return {"answer": task.task_id}

    coordinator.register_agent(
        AgentRole("specialist", capabilities=frozenset({"work"})),
        backend,
    )
    workflow = (
        Workflow("team-runtime", workflow_id="workflow_team_runtime")
        .node(
            "team",
            WorkflowNodeType.AGENT_TEAM,
            metadata={
                "agent_tasks": [
                    {
                        "task_id": "one",
                        "prompt": "first",
                        "required_capabilities": ["work"],
                    },
                    {
                        "task_id": "two",
                        "prompt": "second",
                        "required_capabilities": ["work"],
                    },
                ]
            },
        )
        .compile()
    )
    runtime = CodyRuntime(
        UnusedRunner(),
        multi_agent_coordinator=coordinator,
        max_concurrency=2,
        poll_interval=0,
    )

    run = await runtime.start(workflow, run_id="run_team_runtime")
    result = await run.result()

    assert result.run.status == RunStatus.COMPLETED
    assert result.state.data["agent_outputs"] == {
        "one": {"answer": "one"},
        "two": {"answer": "two"},
    }
    assert len(runtime.stores.artifact_store.list(run_id=run.run_id)) == 3
