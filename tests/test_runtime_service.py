import asyncio

import pytest

from cody.core.runner import CancelledEvent, DoneEvent, TextDeltaEvent
from cody.core.interaction import InteractionRequest
from cody.core.runtime import (
    CodyRuntime,
    RunEvent,
    RunEventType,
    RunStatus,
    RuntimeStoreBundle,
    RuntimeBudget,
    RuntimeRunContext,
    ToolPolicy,
    ToolRegistry,
    ToolSpec,
    Workflow,
    WorkflowCancelled,
    WorkflowPaused,
    WorkflowEdgeType,
    WorkflowNodeType,
    WorkflowWaiting,
)


class FakeResult:
    def __init__(self, output: str):
        self.output = output


class FakeRunner:
    async def run_stream(self, prompt, *, cancel_event=None, **kwargs):
        self.prompt = prompt
        self.kwargs = kwargs
        yield TextDeltaEvent(content="partial ")
        await asyncio.sleep(0)
        if cancel_event is not None and cancel_event.is_set():
            yield CancelledEvent()
            return
        yield DoneEvent(result=FakeResult("final answer"))


@pytest.mark.asyncio
async def test_cody_runtime_executes_agent_as_canonical_workflow_step():
    stores = RuntimeStoreBundle.in_memory()
    runner = FakeRunner()
    runtime = CodyRuntime(runner, stores=stores, poll_interval=0)

    run = await runtime.start("fix the tests", run_id="run_canonical")
    events = [event async for event in run.events()]
    result = await run.result()

    assert result.output == "final answer"
    assert result.run.status == RunStatus.COMPLETED
    assert result.artifact_ids
    assert stores.artifact_store.get(result.artifact_ids[0]).content["output"] == "final answer"
    assert [event.event_type for event in events] == [
        RunEventType.RUN_STARTED,
        RunEventType.SANDBOX_CREATED,
        RunEventType.SANDBOX_STARTED,
        RunEventType.WORKFLOW_STARTED,
        RunEventType.WORKFLOW_NODE_STARTED,
        RunEventType.MODEL_TEXT_DELTA,
            RunEventType.MODEL_COMPLETED,
            RunEventType.WORKFLOW_NODE_COMPLETED,
            RunEventType.WORKFLOW_BATCH_COMPLETED,
            RunEventType.WORKFLOW_COMPLETED,
        RunEventType.SANDBOX_TERMINATED,
        RunEventType.RUN_COMPLETED,
    ]
    assert runner.kwargs["event_scope"] == "step"
    assert runner.prompt == "fix the tests"


@pytest.mark.asyncio
async def test_runtime_tool_policy_also_filters_agent_runner_tools():
    runner = FakeRunner()
    runtime = CodyRuntime(
        runner,
        poll_interval=0,
        tool_policy=ToolPolicy(
            allowed_tools=frozenset({"read_file", "grep"}),
            denied_tools=frozenset({"grep"}),
        ),
    )

    run = await runtime.start(
        "inspect",
        include_tools=["read_file", "grep", "exec_command"],
    )
    await run.result()

    assert runner.kwargs["include_tools"] == ["grep", "read_file"]
    assert runner.kwargs["exclude_tools"] == ["grep"]


@pytest.mark.asyncio
async def test_agent_tool_approval_waits_durably_and_resumes_in_new_runtime(tmp_path):
    class ApprovalRunner:
        workdir = tmp_path

        async def run_events(self, prompt, **kwargs):
            response = await kwargs["interaction_handler"](
                InteractionRequest(
                    id="transient-request-id",
                    kind="confirm",
                    prompt="exec_command: pytest",
                    context={"tool_name": "exec_command", "args": "pytest"},
                )
            )
            assert response.action == "approve"
            yield RunEvent(
                RunEventType.MODEL_COMPLETED,
                run_id=kwargs["run_id"],
                payload={"result": {"output": "approved output"}},
            )

    root = tmp_path / "agent-approval"
    first = CodyRuntime(
        ApprovalRunner(), stores=RuntimeStoreBundle.sqlite(root), poll_interval=0
    )
    waiting = await first.start("run tests", run_id="run_agent_approval")

    with pytest.raises(WorkflowWaiting):
        await waiting.result()

    approvals = first.stores.approval_store.list(run_id=waiting.run_id)
    assert len(approvals) == 1
    assert waiting.done is True
    waiting_events = first.stores.trace_store.list_events(waiting.run_id)
    assert waiting_events[-1].event_type == RunEventType.RUN_WAITING
    assert RunEventType.SANDBOX_SNAPSHOT_CREATED in {
        event.event_type for event in waiting_events
    }
    checkpoint = first.stores.checkpoint_store.latest(waiting.run_id)
    snapshot_artifact_id = checkpoint.metadata["sandbox_snapshot_artifact_id"]
    snapshot_artifact = first.stores.artifact_store.get(snapshot_artifact_id)
    assert snapshot_artifact.artifact_type.value == "sandbox_snapshot"
    first.approve(approvals[0].approval_id, {"action": "approve"})

    second = CodyRuntime(
        ApprovalRunner(), stores=RuntimeStoreBundle.sqlite(root), poll_interval=0
    )
    resumed = await second.resume(waiting.run_id)
    result = await resumed.result()

    assert result.output == "approved output"
    assert result.run.status == RunStatus.COMPLETED
    resumed_events = second.stores.trace_store.list_events(waiting.run_id)
    assert RunEventType.SANDBOX_RESUMED in {
        event.event_type for event in resumed_events
    }


@pytest.mark.asyncio
async def test_runtime_records_governance_context_and_enforces_duration_budget():
    async def slow(_state, _node):
        await asyncio.sleep(1)
        return {"output": "late"}

    workflow = Workflow("budget").node("slow", WorkflowNodeType.FUNCTION).compile()
    runtime = CodyRuntime(
        object(), node_handlers={"function": slow}, poll_interval=0
    )
    handle = await runtime.start(
        workflow,
        {"task": "bounded"},
        context=RuntimeRunContext(
            actor_id="user-1",
            service_account_id="ci-bot",
            project_id="project-1",
            permissions={"tools": ["read_file"]},
        ),
        budget=RuntimeBudget(max_steps=5, max_duration_seconds=0.01),
    )

    with pytest.raises(asyncio.TimeoutError):
        await handle.result()

    record = handle.record
    assert record.status == RunStatus.FAILED
    assert record.project_id == "project-1"
    assert record.metadata["actor_id"] == "user-1"
    assert record.metadata["service_account_id"] == "ci-bot"
    assert record.metadata["budget"]["max_steps"] == 5
    assert record.metadata["permissions"] == {"tools": ["read_file"]}


@pytest.mark.asyncio
async def test_runtime_pause_snapshots_sandbox_and_resumes_next_node(tmp_path):
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def handler(_state, node):
        calls.append(node.node_id)
        if node.node_id == "first":
            entered.set()
            await release.wait()
        return {node.node_id: True}

    workflow = (
        Workflow("pause-sandbox")
        .node("first", WorkflowNodeType.FUNCTION)
        .node("second", WorkflowNodeType.FUNCTION)
        .edge("first", "second")
        .compile()
    )
    runtime = CodyRuntime(
        FakeRunner(),
        stores=RuntimeStoreBundle.sqlite(tmp_path / "pause-runtime"),
        node_handlers={"function": handler},
        poll_interval=0,
    )
    run = await runtime.start(workflow, run_id="run_pause_sandbox")
    await entered.wait()
    run.pause(before_node_id="second")
    release.set()

    with pytest.raises(WorkflowPaused):
        await run.result()
    assert run.record.status == RunStatus.PAUSED
    assert runtime.stores.trace_store.list_events(run.run_id)[-1].event_type == (
        RunEventType.RUN_PAUSED
    )

    resumed = await runtime.resume(run.run_id)
    result = await resumed.result()
    assert result.run.status == RunStatus.COMPLETED
    assert calls == ["first", "second"]


@pytest.mark.asyncio
async def test_cody_runtime_accepts_compiled_workflow_and_structured_input():
    workflow = (
        Workflow("review", workflow_id="workflow_review")
        .node(
            "reviewer",
            WorkflowNodeType.AGENT,
            metadata={"prompt": "Review the implementation."},
        )
        .compile()
    )
    runtime = CodyRuntime(FakeRunner(), poll_interval=0)

    run = await runtime.start(workflow, {"task": "review PR 42"})
    result = await run.result()

    assert result.state.workflow_id == "workflow_review"
    assert "review PR 42" in runtime.runner.prompt
    assert "Review the implementation." in runtime.runner.prompt


@pytest.mark.asyncio
async def test_cody_runtime_cancellation_updates_run_and_emits_terminal_event():
    class BlockingRunner(FakeRunner):
        async def run_stream(self, prompt, *, cancel_event=None, **kwargs):
            yield TextDeltaEvent(content="started")
            while cancel_event is not None and not cancel_event.is_set():
                await asyncio.sleep(0)
            yield CancelledEvent()

    runtime = CodyRuntime(BlockingRunner(), poll_interval=0)
    run = await runtime.start("long task", run_id="run_cancel")
    await asyncio.sleep(0)
    run.cancel()

    with pytest.raises(WorkflowCancelled):
        await run.result()

    assert run.record.status == RunStatus.CANCELLED
    terminal = runtime.stores.trace_store.list_events("run_cancel")[-1]
    assert terminal.event_type == RunEventType.RUN_CANCELLED


@pytest.mark.asyncio
async def test_cody_runtime_sqlite_bundle_persists_complete_vertical_run(tmp_path):
    stores = RuntimeStoreBundle.sqlite(tmp_path / "runtime")
    runtime = CodyRuntime(FakeRunner(), stores=stores, poll_interval=0)

    run = await runtime.start("persist me", run_id="run_durable_service")
    result = await run.result()

    reopened = RuntimeStoreBundle.sqlite(tmp_path / "runtime")
    assert reopened.run_store.get_run(run.run_id).status == RunStatus.COMPLETED
    assert reopened.trace_store.list_events(run.run_id)[-1].event_type == RunEventType.RUN_COMPLETED
    assert reopened.checkpoint_store.latest(run.run_id) is not None
    assert reopened.artifact_store.get(result.artifact_ids[0]).content["output"] == "final answer"


def test_canonical_runtime_is_exported_from_public_sdk_surfaces():
    from cody import CodyRuntime as TopLevelRuntime
    from cody.sdk import CodyRuntime as SDKRuntime

    assert TopLevelRuntime is CodyRuntime
    assert SDKRuntime is CodyRuntime


@pytest.mark.asyncio
async def test_cody_runtime_context_manager_closes_runner_resources():
    class LifecycleRunner(FakeRunner):
        def __init__(self):
            self.stopped = []

        async def stop_mcp(self):
            self.stopped.append("mcp")

        async def stop_lsp(self):
            self.stopped.append("lsp")

    runner = LifecycleRunner()
    async with CodyRuntime(runner, poll_interval=0) as runtime:
        run = await runtime.start("finish normally")
        await run.result()

    assert runner.stopped == ["mcp", "lsp"]


@pytest.mark.asyncio
async def test_waiting_approval_resumes_from_sqlite_in_a_new_runtime_instance(tmp_path):
    root = tmp_path / "recoverable-runtime"
    workflow = (
        Workflow("approval-resume", workflow_id="workflow_approval_resume")
        .node(
            "approval",
            WorkflowNodeType.HUMAN_APPROVAL,
            metadata={"request": {"action": "ship"}},
        )
        .node("agent", WorkflowNodeType.AGENT)
        .edge("approval", "agent")
        .compile()
    )
    first = CodyRuntime(
        FakeRunner(),
        stores=RuntimeStoreBundle.sqlite(root),
        poll_interval=0,
    )
    waiting = await first.start(workflow, {"task": "ship safely"}, run_id="run_resume")

    with pytest.raises(WorkflowWaiting):
        await waiting.result()

    approval = first.stores.approval_store.list(run_id=waiting.run_id)[0]
    assert waiting.record.status == RunStatus.WAITING
    first.approve(approval.approval_id, {"approved": True})

    second = CodyRuntime(
        FakeRunner(),
        stores=RuntimeStoreBundle.sqlite(root),
        poll_interval=0,
    )
    resumed = await second.resume(waiting.run_id)
    result = await resumed.result()

    assert result.run.status == RunStatus.COMPLETED
    assert result.output == "final answer"
    event_types = [
        event.event_type
        for event in second.stores.trace_store.list_events(run_id="run_resume")
    ]
    assert RunEventType.RUN_WAITING in event_types
    assert RunEventType.RUN_RESUMED in event_types
    assert event_types[-1] == RunEventType.RUN_COMPLETED


@pytest.mark.asyncio
async def test_failed_run_retries_from_checkpoint_in_new_runtime_instance(tmp_path):
    root = tmp_path / "retry-runtime"
    workflow = (
        Workflow("retry", workflow_id="workflow_retry")
        .node("work", WorkflowNodeType.FUNCTION)
        .compile()
    )

    def fail(_state, _node):
        raise RuntimeError("transient failure")

    first = CodyRuntime(
        FakeRunner(),
        stores=RuntimeStoreBundle.sqlite(root),
        node_handlers={"function": fail},
    )
    failed = await first.start(workflow, {"task": "retry me"}, run_id="run_retry")
    with pytest.raises(RuntimeError, match="transient failure"):
        await failed.result()
    assert failed.record.status == RunStatus.FAILED

    second = CodyRuntime(
        FakeRunner(),
        stores=RuntimeStoreBundle.sqlite(root),
        node_handlers={"function": lambda _state, _node: {"recovered": True}},
    )
    retried = await second.retry(failed.run_id)
    result = await retried.result()

    assert result.run.status == RunStatus.COMPLETED
    assert result.state.data["recovered"] is True
    event_types = [
        event.event_type
        for event in second.stores.trace_store.list_events(run_id=failed.run_id)
    ]
    assert RunEventType.RUN_RETRYING in event_types
    assert event_types[-1] == RunEventType.RUN_COMPLETED


@pytest.mark.asyncio
async def test_runtime_forks_historical_checkpoint_with_run_lineage(tmp_path):
    root = tmp_path / "fork-runtime"
    source_calls = []
    workflow = (
        Workflow("fork", workflow_id="workflow_runtime_fork")
        .node("first", WorkflowNodeType.FUNCTION)
        .node("second", WorkflowNodeType.FUNCTION)
        .edge("first", "second")
        .compile()
    )

    def source_handler(_state, node):
        source_calls.append(node.node_id)
        return {node.node_id: True}

    first = CodyRuntime(
        FakeRunner(),
        stores=RuntimeStoreBundle.sqlite(root),
        node_handlers={"function": source_handler},
    )
    source = await first.start(workflow, run_id="run_fork_source")
    await source.result()
    checkpoint = next(
        checkpoint
        for checkpoint in first.stores.checkpoint_store.list_checkpoints(source.run_id)
        if checkpoint.step_id == "scheduler_batch_000001"
    )

    fork_calls = []

    def fork_handler(_state, node):
        fork_calls.append(node.node_id)
        return {f"fork_{node.node_id}": True}

    second = CodyRuntime(
        FakeRunner(),
        stores=RuntimeStoreBundle.sqlite(root),
        node_handlers={"function": fork_handler},
    )
    forked = await second.fork(
        checkpoint.checkpoint_id,
        new_run_id="run_fork_child",
        metadata={"reason": "alternate path"},
    )
    result = await forked.result()

    assert source_calls == ["first", "second"]
    assert fork_calls == ["second"]
    assert result.run.parent_run_id == source.run_id
    assert result.run.metadata["reason"] == "alternate path"
    assert result.run.status == RunStatus.COMPLETED
    child_events = second.stores.trace_store.list_events(forked.run_id)
    assert child_events[0].event_type == RunEventType.RUN_FORKED
    assert child_events[-1].event_type == RunEventType.RUN_COMPLETED


@pytest.mark.asyncio
async def test_tool_receipt_prevents_duplicate_side_effect_during_retry(tmp_path):
    root = tmp_path / "idempotent-runtime"
    calls = []
    registry = ToolRegistry()

    def side_effect(args, _state, _node):
        calls.append(dict(args))
        return {"changed": True}

    registry.register(
        ToolSpec(
            "side_effect",
            side_effect,
            required_args=("path",),
            metadata={"idempotency_arg": "request_id"},
        )
    )
    workflow = (
        Workflow("idempotent", workflow_id="workflow_idempotent")
        .node(
            "write",
            WorkflowNodeType.TOOL,
            tool_name="side_effect",
            metadata={"args": {"path": "result.txt"}},
        )
        .node("finish", WorkflowNodeType.FUNCTION)
        .edge("write", "finish")
        .compile()
    )

    def fail(_state, _node):
        raise RuntimeError("crash after side effect")

    first = CodyRuntime(
        FakeRunner(),
        stores=RuntimeStoreBundle.sqlite(root),
        tool_registry=registry,
        node_handlers={"function": fail},
    )
    failed = await first.start(workflow, run_id="run_idempotent")
    with pytest.raises(RuntimeError, match="crash after side effect"):
        await failed.result()
    initial_checkpoint = next(
        checkpoint
        for checkpoint in first.stores.checkpoint_store.list_checkpoints(failed.run_id)
        if checkpoint.step_id == "scheduler_start"
    )
    assert len(calls) == 1
    assert calls[0]["request_id"].startswith("runtime-tool:")

    second = CodyRuntime(
        FakeRunner(),
        stores=RuntimeStoreBundle.sqlite(root),
        tool_registry=registry,
        node_handlers={"function": lambda _state, _node: {"finished": True}},
    )
    retried = await second.retry(
        failed.run_id,
        checkpoint_id=initial_checkpoint.checkpoint_id,
    )
    result = await retried.result()

    assert result.state.data["finished"] is True
    assert len(calls) == 1
    replay_events = [
        event
        for event in second.stores.trace_store.list_events(failed.run_id)
        if event.event_type == RunEventType.TOOL_CALL_COMPLETED
        and event.payload.get("replayed") is True
    ]
    assert len(replay_events) == 1


@pytest.mark.asyncio
async def test_cody_runtime_uses_concurrent_scheduler_for_parallel_graph():
    started = set()
    gate = asyncio.Event()

    async def handler(_state, node):
        if node.node_id in {"left", "right"}:
            started.add(node.node_id)
            if len(started) == 2:
                gate.set()
            await asyncio.wait_for(gate.wait(), timeout=0.2)
        return {node.node_id: True}

    workflow = (
        Workflow("runtime-parallel", workflow_id="workflow_runtime_parallel")
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
    runtime = CodyRuntime(
        FakeRunner(),
        node_handlers={"function": handler},
        max_concurrency=2,
        poll_interval=0,
    )

    run = await runtime.start(workflow, run_id="run_runtime_parallel")
    result = await run.result()

    assert started == {"left", "right"}
    assert result.run.status == RunStatus.COMPLETED
    event_types = [
        event.event_type for event in runtime.stores.trace_store.list_events(run.run_id)
    ]
    assert RunEventType.WORKFLOW_BATCH_COMPLETED in event_types
