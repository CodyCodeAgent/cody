import asyncio

import pytest

from cody.core.runtime import (
    AsyncWorkflowScheduleError,
    AsyncWorkflowScheduler,
    RunEventType,
    Workflow,
    WorkflowCancelled,
    WorkflowEdgeType,
    WorkflowNodeType,
)


def parallel_join_workflow(*, metadata=None):
    return (
        Workflow(
            "parallel",
            workflow_id="workflow_parallel",
            metadata=metadata or {},
        )
        .node("start", WorkflowNodeType.FUNCTION)
        .node("left", WorkflowNodeType.FUNCTION)
        .node("right", WorkflowNodeType.FUNCTION)
        .node("join", WorkflowNodeType.FUNCTION)
        .edge("start", "left", edge_type=WorkflowEdgeType.PARALLEL)
        .edge("start", "right", edge_type=WorkflowEdgeType.PARALLEL)
        .edge("left", "join", edge_type=WorkflowEdgeType.JOIN)
        .edge("right", "join", edge_type=WorkflowEdgeType.JOIN)
        .compile()
    )


@pytest.mark.asyncio
async def test_async_scheduler_runs_ready_branches_concurrently_and_joins():
    started = set()
    both_started = asyncio.Event()
    join_inputs = []

    async def handler(state, node):
        if node.node_id in {"left", "right"}:
            started.add(node.node_id)
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=0.2)
            return {node.node_id: f"{node.node_id}-output"}
        if node.node_id == "join":
            join_inputs.append(dict(state.data))
            return {"joined": True}
        return {"started": True}

    scheduler = AsyncWorkflowScheduler(
        node_handlers={"function": handler},
        max_concurrency=2,
    )
    state = await scheduler.run(parallel_join_workflow(), run_id="run_parallel")

    assert started == {"left", "right"}
    assert join_inputs == [
        {
            "started": True,
            "left": "left-output",
            "right": "right-output",
        }
    ]
    assert state.data["joined"] is True
    assert state.completed_node_ids == ["start", "left", "right", "join"]
    batch_events = [
        event
        for event in scheduler.trace_store.list_events("run_parallel")
        if event.event_type == RunEventType.WORKFLOW_BATCH_COMPLETED
    ]
    assert len(batch_events) == 3


@pytest.mark.asyncio
async def test_async_scheduler_retries_timed_out_node_with_bound():
    attempts = 0
    workflow = (
        Workflow("retry-timeout", workflow_id="workflow_retry_timeout")
        .node(
            "primary",
            WorkflowNodeType.FUNCTION,
            metadata={"timeout_seconds": 0.01, "max_retries": 1},
        )
        .node("done", WorkflowNodeType.FUNCTION)
        .node("fallback", WorkflowNodeType.FUNCTION)
        .edge("primary", "done")
        .edge("primary", "fallback", edge_type=WorkflowEdgeType.FALLBACK)
        .compile()
    )

    async def handler(_state, node):
        nonlocal attempts
        if node.node_id == "primary":
            attempts += 1
            if attempts == 1:
                await asyncio.sleep(0.05)
            return {"primary_ok": True}
        return {node.node_id: True}

    scheduler = AsyncWorkflowScheduler(node_handlers={"function": handler})
    state = await scheduler.run(workflow, run_id="run_retry_timeout")

    assert attempts == 2
    assert state.completed_node_ids == ["primary", "done"]
    assert "fallback" not in state.completed_node_ids
    retry_events = [
        event
        for event in scheduler.trace_store.list_events("run_retry_timeout")
        if event.event_type == RunEventType.WORKFLOW_NODE_RETRYING
    ]
    assert len(retry_events) == 1


@pytest.mark.asyncio
async def test_async_scheduler_routes_terminal_failure_to_fallback():
    workflow = (
        Workflow("fallback", workflow_id="workflow_async_fallback")
        .node("primary", WorkflowNodeType.FUNCTION)
        .node("fallback", WorkflowNodeType.FUNCTION)
        .edge("primary", "fallback", edge_type=WorkflowEdgeType.FALLBACK)
        .compile()
    )

    async def handler(_state, node):
        if node.node_id == "primary":
            raise RuntimeError("primary failed")
        return {"recovered": True}

    scheduler = AsyncWorkflowScheduler(node_handlers={"function": handler})
    state = await scheduler.run(workflow, run_id="run_fallback")

    assert state.failed_node_ids == ["primary"]
    assert state.completed_node_ids == ["fallback"]
    assert state.data["recovered"] is True


@pytest.mark.asyncio
async def test_async_scheduler_cancels_running_parallel_tasks():
    cancel_event = asyncio.Event()
    both_started = asyncio.Event()
    started = set()
    cancelled = set()

    async def handler(_state, node):
        if node.node_id == "start":
            return {}
        started.add(node.node_id)
        if len(started) == 2:
            both_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.add(node.node_id)
            raise

    scheduler = AsyncWorkflowScheduler(
        node_handlers={"function": handler},
        cancel_event=cancel_event,
        max_concurrency=2,
    )
    execution = asyncio.create_task(
        scheduler.run(parallel_join_workflow(), run_id="run_cancel_parallel")
    )
    await asyncio.wait_for(both_started.wait(), timeout=0.2)
    cancel_event.set()

    with pytest.raises(WorkflowCancelled):
        await asyncio.wait_for(execution, timeout=0.2)

    assert cancelled == {"left", "right"}
    latest = scheduler.checkpoint_store.latest("run_cancel_parallel")
    assert latest.workflow_state["scheduler_ready_node_ids"] == ["left", "right"]


@pytest.mark.asyncio
async def test_async_scheduler_rejects_ambiguous_parallel_output_merge():
    async def handler(_state, node):
        if node.node_id == "start":
            return {}
        if node.node_id == "join":
            return {}
        return {"same_key": node.node_id}

    scheduler = AsyncWorkflowScheduler(node_handlers={"function": handler})

    with pytest.raises(AsyncWorkflowScheduleError, match="Parallel output conflict"):
        await scheduler.run(parallel_join_workflow(), run_id="run_conflict")


@pytest.mark.asyncio
async def test_async_scheduler_resume_uses_last_safe_batch_checkpoint():
    workflow = (
        Workflow("recover-batch", workflow_id="workflow_recover_batch")
        .node("primary", WorkflowNodeType.FUNCTION)
        .node("fallback", WorkflowNodeType.FUNCTION)
        .edge("primary", "fallback", edge_type=WorkflowEdgeType.FALLBACK)
        .compile()
    )

    async def fail(_state, _node):
        raise RuntimeError("worker crashed")

    first = AsyncWorkflowScheduler(node_handlers={"function": fail})
    with pytest.raises(RuntimeError, match="worker crashed"):
        await first.run(workflow, run_id="run_safe_checkpoint")

    checkpoint = first.checkpoint_store.latest("run_safe_checkpoint")
    assert checkpoint.metadata["scheduler_safe_boundary"] is True

    second = AsyncWorkflowScheduler(
        node_handlers={"function": lambda _state, node: {node.node_id: True}},
        trace_store=first.trace_store,
        checkpoint_store=first.checkpoint_store,
    )
    resumed = await second.resume(workflow, checkpoint=checkpoint)
    assert resumed.data["fallback"] is True
    assert resumed.failed_node_ids == ["primary"]


@pytest.mark.asyncio
async def test_async_scheduler_executes_nested_workflow_without_semaphore_deadlock():
    child = (
        Workflow("child", workflow_id="workflow_nested_child")
        .node("child_one", WorkflowNodeType.FUNCTION)
        .node("child_two", WorkflowNodeType.FUNCTION)
        .edge("child_one", "child_two")
        .compile()
    )
    parent = (
        Workflow("parent", workflow_id="workflow_nested_parent")
        .node(
            "nested",
            WorkflowNodeType.NESTED_WORKFLOW,
            metadata={"workflow_id": child.workflow_id},
        )
        .node("done", WorkflowNodeType.FUNCTION)
        .edge("nested", "done")
        .compile()
    )

    async def handler(_state, node):
        return {node.node_id: True}

    scheduler = AsyncWorkflowScheduler(
        node_handlers={"function": handler},
        nested_workflows={child.workflow_id: child},
        max_concurrency=1,
    )
    state = await asyncio.wait_for(
        scheduler.run(parent, run_id="run_nested_async"),
        timeout=0.2,
    )

    assert state.data["done"] is True
    assert state.data["nested_result"]["child_one"] is True
    assert state.data["nested_result"]["child_two"] is True
    assert state.data["child_run_ids"] == ["run_nested_async_nested"]
