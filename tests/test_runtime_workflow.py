import pytest

from cody.core.runtime import Workflow, WorkflowEdgeType, WorkflowNodeType


def test_workflow_compile_and_initial_state():
    workflow = (
        Workflow("feature_dev", workflow_id="workflow_feature")
        .node("plan", WorkflowNodeType.AGENT, agent_name="planner")
        .node("code", WorkflowNodeType.AGENT, agent_name="coder")
        .node("test", WorkflowNodeType.TOOL, tool_name="pytest")
        .edge("plan", "code")
        .conditional_edge("code", "test", condition="implementation_complete", label="ready")
    )

    compiled = workflow.compile()
    state = compiled.initial_state("run_1", data={"task": "build runtime"})

    assert compiled.workflow_id == "workflow_feature"
    assert compiled.entry_node_id == "plan"
    assert compiled.nodes["code"].agent_name == "coder"
    assert compiled.outgoing("code")[0].edge_type == WorkflowEdgeType.CONDITIONAL
    assert compiled.outgoing("code")[0].condition == "implementation_complete"
    assert compiled.incoming("test")[0].source == "code"
    assert state.workflow_id == "workflow_feature"
    assert state.run_id == "run_1"
    assert state.current_node_id == "plan"
    assert state.data == {"task": "build runtime"}


def test_workflow_to_dict_is_json_shaped():
    compiled = (
        Workflow("review", workflow_id="workflow_review", metadata={"version": 1})
        .node("review", WorkflowNodeType.AGENT, name="Review", agent_name="reviewer")
        .node("approval", WorkflowNodeType.HUMAN_APPROVAL, name="Approve")
        .edge("review", "approval", edge_type=WorkflowEdgeType.SEQUENTIAL)
        .compile()
    )

    data = compiled.to_dict()

    assert data["workflow_id"] == "workflow_review"
    assert data["metadata"] == {"version": 1}
    assert data["nodes"]["review"]["node_type"] == "agent"
    assert data["edges"][0]["edge_type"] == "sequential"


def test_workflow_rejects_duplicate_nodes():
    workflow = Workflow("bad").node("plan", WorkflowNodeType.AGENT)

    with pytest.raises(ValueError, match="Duplicate workflow node"):
        workflow.node("plan", WorkflowNodeType.TOOL)


def test_workflow_rejects_missing_edge_endpoints():
    workflow = Workflow("bad").node("plan", WorkflowNodeType.AGENT).edge("plan", "missing")

    with pytest.raises(ValueError, match="target does not exist"):
        workflow.compile()


def test_workflow_rejects_conditional_edge_without_condition():
    workflow = (
        Workflow("bad")
        .node("plan", WorkflowNodeType.AGENT)
        .node("code", WorkflowNodeType.AGENT)
        .edge("plan", "code", edge_type=WorkflowEdgeType.CONDITIONAL)
    )

    with pytest.raises(ValueError, match="Conditional workflow edges"):
        workflow.compile()


def test_workflow_executor_runs_nodes_and_records_trace_and_checkpoints():
    from cody.core.runtime import InMemoryCheckpointStore, InMemoryTraceStore, WorkflowExecutor

    workflow = (
        Workflow("feature", workflow_id="workflow_exec")
        .node("plan", WorkflowNodeType.AGENT)
        .node("code", WorkflowNodeType.AGENT)
        .edge("plan", "code")
        .compile()
    )
    trace_store = InMemoryTraceStore()
    checkpoint_store = InMemoryCheckpointStore()
    executor = WorkflowExecutor(
        trace_store=trace_store,
        checkpoint_store=checkpoint_store,
        node_handlers={
            "plan": lambda state, node: {"plan": "ok"},
            "code": lambda state, node: {"code": "done"},
        },
    )

    final_state = executor.run(workflow, run_id="run_workflow", initial_data={"task": "ship"})

    assert final_state.current_node_id is None
    assert final_state.completed_node_ids == ["plan", "code"]
    assert final_state.data == {"task": "ship", "plan": "ok", "code": "done"}
    event_types = [event.event_type.value for event in trace_store.list_events("run_workflow")]
    assert event_types == [
        "workflow.started",
        "workflow.node.started",
        "workflow.node.completed",
        "workflow.edge.selected",
        "workflow.node.started",
        "workflow.node.completed",
        "workflow.completed",
    ]
    assert checkpoint_store.latest("run_workflow") is not None
    assert trace_store.list_events("run_workflow")[0].payload["checkpoint_id"]


def test_workflow_executor_selects_condition_true_edge():
    from cody.core.runtime import WorkflowExecutor

    workflow = (
        Workflow("conditional")
        .node("test", WorkflowNodeType.TOOL)
        .node("fix", WorkflowNodeType.AGENT)
        .node("done", WorkflowNodeType.CHECKPOINT)
        .conditional_edge("test", "fix", condition="failed")
        .edge("test", "done")
        .compile()
    )
    executor = WorkflowExecutor(condition_handlers={"failed": lambda state, edge: True})

    final_state = executor.run(workflow, run_id="run_condition")

    assert final_state.completed_node_ids == ["test", "fix"]


def test_workflow_executor_requires_condition_handler():
    from cody.core.runtime import WorkflowExecutionError, WorkflowExecutor

    workflow = (
        Workflow("conditional")
        .node("test", WorkflowNodeType.TOOL)
        .node("fix", WorkflowNodeType.AGENT)
        .conditional_edge("test", "fix", condition="failed")
        .compile()
    )

    with pytest.raises(WorkflowExecutionError, match="No condition handler"):
        WorkflowExecutor().run(workflow, run_id="run_missing_condition")


def test_workflow_executor_stops_at_max_steps():
    from cody.core.runtime import WorkflowExecutionError, WorkflowExecutor

    workflow = (
        Workflow("loop")
        .node("again", WorkflowNodeType.FUNCTION)
        .edge("again", "again")
        .compile()
    )

    with pytest.raises(WorkflowExecutionError, match="max_steps"):
        WorkflowExecutor().run(workflow, run_id="run_loop", max_steps=2)


def test_workflow_executor_runs_agent_tool_and_approval_adapters():
    from cody.core.runtime import (
        WorkflowExecutor,
        agent_node_handler,
        human_approval_node_handler,
        tool_node_handler,
    )

    workflow = (
        Workflow("adapter_flow")
        .node("plan", WorkflowNodeType.AGENT, metadata={"prompt": "plan it"})
        .node("read", WorkflowNodeType.TOOL, tool_name="read_file", metadata={"args": {"path": "README.md"}})
        .node("approve", WorkflowNodeType.HUMAN_APPROVAL, metadata={"request": {"action": "merge"}})
        .edge("plan", "read")
        .edge("read", "approve")
        .compile()
    )

    prompts = []
    tool_calls = []
    approvals = []

    executor = WorkflowExecutor(node_handlers={
        "agent": agent_node_handler(lambda prompt, state, node: prompts.append(prompt) or {"plan": "ok"}),
        "tool": tool_node_handler(
            lambda tool_name, args, state, node: tool_calls.append((tool_name, args)) or "file contents"
        ),
        "human_approval": human_approval_node_handler(
            lambda request, state, node: approvals.append(request) or True
        ),
    })

    final_state = executor.run(workflow, run_id="run_adapters")

    assert prompts == ["plan it"]
    assert tool_calls == [("read_file", {"path": "README.md"})]
    assert approvals == [{"action": "merge"}]
    assert final_state.data == {
        "plan": "ok",
        "tool_output": "file contents",
        "approved": True,
    }


def test_tool_adapter_requires_tool_name_and_dict_args():
    from cody.core.runtime import WorkflowExecutionError, WorkflowExecutor, tool_node_handler

    workflow = Workflow("bad_tool").node("tool", WorkflowNodeType.TOOL).compile()
    executor = WorkflowExecutor(node_handlers={"tool": tool_node_handler(lambda *args: {})})

    with pytest.raises(WorkflowExecutionError, match="missing tool_name"):
        executor.run(workflow, run_id="run_bad_tool")

    workflow_args = (
        Workflow("bad_args")
        .node("tool", WorkflowNodeType.TOOL, tool_name="read_file", metadata={"args": "README.md"})
        .compile()
    )
    with pytest.raises(WorkflowExecutionError, match="args must be a dict"):
        executor.run(workflow_args, run_id="run_bad_args")


def test_human_approval_adapter_requires_dict_request():
    from cody.core.runtime import WorkflowExecutionError, WorkflowExecutor, human_approval_node_handler

    workflow = (
        Workflow("bad_approval")
        .node("approve", WorkflowNodeType.HUMAN_APPROVAL, metadata={"request": "merge"})
        .compile()
    )
    executor = WorkflowExecutor(node_handlers={
        "human_approval": human_approval_node_handler(lambda request, state, node: True)
    })

    with pytest.raises(WorkflowExecutionError, match="request must be a dict"):
        executor.run(workflow, run_id="run_bad_approval")


def test_coding_workflow_template_executes_happy_path_with_adapters():
    from cody.core.runtime import (
        WorkflowExecutor,
        agent_node_handler,
        coding_workflow_template,
        human_approval_node_handler,
        tool_node_handler,
    )

    workflow = coding_workflow_template().compile()
    seen_prompts = []
    seen_tools = []

    executor = WorkflowExecutor(
        node_handlers={
            "agent": agent_node_handler(
                lambda prompt, state, node: seen_prompts.append((node.node_id, prompt)) or {node.node_id: "done"}
            ),
            "tool": tool_node_handler(
                lambda tool_name, args, state, node: seen_tools.append((tool_name, args)) or {"tests_passed": True}
            ),
            "human_approval": human_approval_node_handler(lambda request, state, node: {"approved": True}),
        },
        condition_handlers={
            "tests_failed": lambda state, edge: False,
            "review_requested_changes": lambda state, edge: False,
        },
    )

    final_state = executor.run(workflow, run_id="run_coding_template", initial_data={"task": "ship"})

    assert final_state.completed_node_ids == ["plan", "implement", "test", "review", "approval"]
    assert seen_tools == [("exec_command", {"command": "pytest"})]
    assert seen_prompts[0][0] == "plan"
    assert final_state.data["approved"] is True


def test_coding_workflow_template_routes_to_fix_when_tests_fail():
    from cody.core.runtime import WorkflowExecutor, agent_node_handler, coding_workflow_template, tool_node_handler

    workflow = coding_workflow_template().compile()
    attempts = {"tests": 0}

    def tests_failed(state, edge):
        return attempts["tests"] == 1

    def run_tool(tool_name, args, state, node):
        attempts["tests"] += 1
        return {"tests_passed": attempts["tests"] > 1}

    executor = WorkflowExecutor(
        node_handlers={
            "agent": agent_node_handler(lambda prompt, state, node: {node.node_id: "done"}),
            "tool": tool_node_handler(run_tool),
            "human_approval": lambda state, node: {"approved": True},
        },
        condition_handlers={
            "tests_failed": tests_failed,
            "review_requested_changes": lambda state, edge: False,
        },
    )

    final_state = executor.run(workflow, run_id="run_coding_fix")

    assert final_state.completed_node_ids == [
        "plan", "implement", "test", "fix", "test", "review", "approval"
    ]
    assert attempts["tests"] == 2


def test_refactor_workflow_template_compiles_expected_shape():
    from cody.core.runtime import refactor_workflow_template

    workflow = refactor_workflow_template(workflow_id="workflow_refactor_test").compile()

    assert workflow.workflow_id == "workflow_refactor_test"
    assert workflow.entry_node_id == "analyze"
    assert set(workflow.nodes) == {"analyze", "safety_tests", "refactor", "test", "review"}
    assert any(edge.condition == "tests_failed" for edge in workflow.outgoing("test"))


def test_run_coding_workflow_high_level_api_happy_path():
    from cody.core.runtime import InMemoryCheckpointStore, InMemoryTraceStore, run_coding_workflow

    trace_store = InMemoryTraceStore()
    checkpoint_store = InMemoryCheckpointStore()

    state = run_coding_workflow(
        task="ship feature",
        run_id="run_high_level_coding",
        trace_store=trace_store,
        checkpoint_store=checkpoint_store,
        run_agent=lambda prompt, state, node: {node.node_id: "done"},
        call_tool=lambda tool_name, args, state, node: {"tests_passed": True},
        request_approval=lambda request, state, node: True,
    )

    assert state.completed_node_ids == ["plan", "implement", "test", "review", "approval"]
    assert state.data["task"] == "ship feature"
    assert state.data["approved"] is True
    assert trace_store.list_events("run_high_level_coding")
    assert checkpoint_store.latest("run_high_level_coding") is not None


def test_run_coding_workflow_high_level_api_uses_fix_loop():
    from cody.core.runtime import run_coding_workflow

    attempts = {"tests": 0}

    def call_tool(tool_name, args, state, node):
        attempts["tests"] += 1
        return {"tests_passed": attempts["tests"] > 1}

    state = run_coding_workflow(
        task="fix feature",
        run_id="run_high_level_fix",
        run_agent=lambda prompt, state, node: {node.node_id: "done"},
        call_tool=call_tool,
        request_approval=lambda request, state, node: True,
    )

    assert state.completed_node_ids == ["plan", "implement", "test", "fix", "test", "review", "approval"]
    assert attempts["tests"] == 2


def test_run_refactor_workflow_high_level_api():
    from cody.core.runtime import run_refactor_workflow

    state = run_refactor_workflow(
        task="refactor auth",
        run_id="run_high_level_refactor",
        run_agent=lambda prompt, state, node: {node.node_id: "done"},
        call_tool=lambda tool_name, args, state, node: {"tests_passed": True},
    )

    assert state.completed_node_ids == ["analyze", "safety_tests", "refactor", "test", "review"]
    assert state.data["task"] == "refactor auth"


def test_high_level_workflow_runs_with_cody_native_backends():
    from cody.core.runtime import (
        agent_runner_backend,
        run_coding_workflow,
        static_approval_backend,
        tool_mapping_backend,
    )

    class FakeResult:
        def __init__(self, output):
            self.output = output

    class FakeRunner:
        def __init__(self):
            self.prompts = []

        def run_sync(self, prompt):
            self.prompts.append(prompt)
            return FakeResult(f"handled: {prompt}")

    runner = FakeRunner()
    tool_calls = []

    state = run_coding_workflow(
        task="ship native backend",
        run_id="run_native_backends",
        run_agent=agent_runner_backend(runner),
        call_tool=tool_mapping_backend({
            "exec_command": lambda args, state, node: tool_calls.append(args) or {"tests_passed": True}
        }),
        request_approval=static_approval_backend(approved=True),
    )

    assert state.completed_node_ids == ["plan", "implement", "test", "review", "approval"]
    assert len(runner.prompts) == 3
    assert tool_calls == [{"command": "pytest"}]
    assert state.data["approved"] is True
    assert state.data["approval_request"] == {"action": "approve_final_diff"}


def test_tool_mapping_backend_raises_for_missing_tool():
    from cody.core.runtime import run_coding_workflow, static_approval_backend, tool_mapping_backend

    with pytest.raises(KeyError, match="No workflow tool backend"):
        run_coding_workflow(
            task="missing tool",
            run_id="run_missing_tool",
            run_agent=lambda prompt, state, node: {node.node_id: "done"},
            call_tool=tool_mapping_backend({}),
            request_approval=static_approval_backend(),
        )


def test_async_workflow_executor_runs_async_handlers_and_conditions():
    import asyncio

    from cody.core.runtime import AsyncWorkflowExecutor, Workflow, WorkflowEdgeType, WorkflowNodeType

    workflow = (
        Workflow(name="async_workflow", workflow_id="workflow_async")
        .node("start", WorkflowNodeType.AGENT)
        .node("fix", WorkflowNodeType.AGENT)
        .node("done", WorkflowNodeType.TOOL)
        .edge("start", "fix", edge_type=WorkflowEdgeType.CONDITIONAL, condition="needs_fix")
        .edge("start", "done")
        .edge("fix", "done")
        .compile()
    )

    async def agent_handler(state, node):
        if node.node_id == "start":
            return {"needs_fix": True}
        return {"fixed": True, "needs_fix": False}

    async def tool_handler(state, node):
        return {"done": node.node_id}

    async def needs_fix(state, edge):
        return bool(state.data.get("needs_fix"))

    async def run():
        executor = AsyncWorkflowExecutor(
            node_handlers={"agent": agent_handler, "tool": tool_handler},
            condition_handlers={"needs_fix": needs_fix},
        )
        state = await executor.run(workflow, run_id="run_async")
        return state, executor

    state, executor = asyncio.run(run())

    assert state.completed_node_ids == ["start", "fix", "done"]
    assert state.data["fixed"] is True
    assert state.data["done"] == "done"
    assert [event.event_type.value for event in executor.trace_store.list_events(run_id="run_async")][0] == "workflow.started"


def test_agent_runner_streaming_backend_collects_and_traces_stream_events():
    import asyncio

    from cody.core.runner import DoneEvent, TextDeltaEvent
    from cody.core.runtime import InMemoryTraceStore, WorkflowNode, WorkflowNodeType, WorkflowState, agent_runner_streaming_backend

    class FakeResult:
        output = "final answer"

    class FakeRunner:
        async def run_stream(self, prompt, run_id=None, **kwargs):
            self.prompt = prompt
            self.run_id = run_id
            self.kwargs = kwargs
            yield TextDeltaEvent(content="partial ")
            yield TextDeltaEvent(content="answer")
            yield DoneEvent(result=FakeResult())

    async def run():
        trace_store = InMemoryTraceStore()
        runner = FakeRunner()
        backend = agent_runner_streaming_backend(runner, trace_store=trace_store)
        state = WorkflowState(workflow_id="workflow_stream", run_id="run_stream_backend")
        node = WorkflowNode(node_id="agent", node_type=WorkflowNodeType.AGENT)
        output = await backend("do work", state, node)
        return output, trace_store, runner

    output, trace_store, runner = asyncio.run(run())

    assert output["agent_output"] == "final answer"
    assert [event["event_type"] for event in output["agent_stream_events"]] == ["text_delta", "text_delta", "done"]
    assert runner.prompt == "do work"
    assert runner.run_id == "run_stream_backend"
    assert runner.kwargs == {
        "event_scope": "step",
        "step_id_prefix": "node_agent_model",
    }
    mirrored = trace_store.list_events(run_id="run_stream_backend")
    assert [event.step_id for event in mirrored] == [
        "agent_stream_000001",
        "agent_stream_000002",
        "agent_stream_000003",
    ]
    assert mirrored[-1].event_type.value == "model.completed"


def test_workflow_executor_resumes_from_checkpoint_without_replaying_completed_nodes():
    from cody.core.runtime import CheckpointRecord, Workflow, WorkflowExecutor, WorkflowNodeType

    workflow = (
        Workflow(name="resume_workflow", workflow_id="workflow_resume")
        .node("plan", WorkflowNodeType.AGENT)
        .node("implement", WorkflowNodeType.AGENT)
        .node("test", WorkflowNodeType.TOOL)
        .edge("plan", "implement")
        .edge("implement", "test")
        .compile()
    )
    checkpoint = CheckpointRecord(
        run_id="run_resume",
        step_id="node_plan_completed",
        workflow_state={
            "workflow_id": "workflow_resume",
            "run_id": "run_resume",
            "current_node_id": "implement",
            "data": {"plan": "done"},
            "completed_node_ids": ["plan"],
            "failed_node_ids": [],
            "artifact_refs": [],
        },
    )
    executed = []

    def handler(state, node):
        executed.append(node.node_id)
        return {node.node_id: "done"}

    executor = WorkflowExecutor(node_handlers={"agent": handler, "tool": handler})
    state = executor.resume(workflow, checkpoint=checkpoint)

    assert executed == ["implement", "test"]
    assert state.completed_node_ids == ["plan", "implement", "test"]
    assert state.data == {"plan": "done", "implement": "done", "test": "done"}
    assert [event.event_type.value for event in executor.trace_store.list_events(run_id="run_resume")][0] == "workflow.resumed"


def test_async_workflow_executor_resumes_from_checkpoint():
    import asyncio

    from cody.core.runtime import AsyncWorkflowExecutor, CheckpointRecord, Workflow, WorkflowNodeType

    workflow = (
        Workflow(name="async_resume", workflow_id="workflow_async_resume")
        .node("start", WorkflowNodeType.AGENT)
        .node("finish", WorkflowNodeType.TOOL)
        .edge("start", "finish")
        .compile()
    )
    checkpoint = CheckpointRecord(
        run_id="run_async_resume",
        step_id="node_start_completed",
        workflow_state={
            "workflow_id": "workflow_async_resume",
            "run_id": "run_async_resume",
            "current_node_id": "finish",
            "data": {"start": "done"},
            "completed_node_ids": ["start"],
        },
    )

    async def handler(state, node):
        return {node.node_id: "done"}

    async def run():
        executor = AsyncWorkflowExecutor(node_handlers={"agent": handler, "tool": handler})
        state = await executor.resume(workflow, checkpoint=checkpoint)
        return state, executor

    state, executor = asyncio.run(run())

    assert state.completed_node_ids == ["start", "finish"]
    assert state.data["finish"] == "done"
    assert executor.trace_store.list_events(run_id="run_async_resume")[0].event_type.value == "workflow.resumed"


def test_workflow_executor_rejects_checkpoint_for_different_workflow():
    import pytest

    from cody.core.runtime import CheckpointRecord, Workflow, WorkflowExecutionError, WorkflowExecutor, WorkflowNodeType

    workflow = Workflow(name="target", workflow_id="workflow_target").node("start", WorkflowNodeType.AGENT).compile()
    checkpoint = CheckpointRecord(
        run_id="run_bad_resume",
        step_id="bad",
        workflow_state={
            "workflow_id": "workflow_other",
            "run_id": "run_bad_resume",
            "current_node_id": "start",
        },
    )

    with pytest.raises(WorkflowExecutionError, match="workflow_id mismatch"):
        WorkflowExecutor().resume(workflow, checkpoint=checkpoint)


def test_workflow_run_manager_starts_and_resumes_latest_checkpoint():
    from cody.core.runtime import Workflow, WorkflowNodeType, WorkflowRunManager

    workflow = (
        Workflow(name="managed", workflow_id="workflow_managed")
        .node("one", WorkflowNodeType.AGENT)
        .node("two", WorkflowNodeType.AGENT)
        .edge("one", "two")
        .compile()
    )
    calls = []

    def handler(state, node):
        calls.append(node.node_id)
        if node.node_id == "one":
            return {"one": True}
        return {"two": True}

    import pytest

    from cody.core.runtime import WorkflowExecutionError

    manager = WorkflowRunManager(node_handlers={"agent": handler})
    with pytest.raises(WorkflowExecutionError, match="max_steps"):
        manager.start(workflow, run_id="run_managed", max_steps=1)

    assert calls == ["one"]

    resumed = manager.resume_latest(workflow, run_id="run_managed")

    assert calls == ["one", "two"]
    assert resumed.completed_node_ids == ["one", "two"]
    assert manager.latest_checkpoint("run_managed") is not None
    assert manager.events("run_managed")[0].event_type.value == "workflow.started"
    assert any(event.event_type.value == "workflow.resumed" for event in manager.events("run_managed"))


def test_workflow_run_manager_forks_from_checkpoint_with_lineage():
    from cody.core.runtime import Workflow, WorkflowNodeType, WorkflowRunManager

    workflow = Workflow(name="forkable", workflow_id="workflow_forkable").node("start", WorkflowNodeType.AGENT).compile()
    manager = WorkflowRunManager(node_handlers={"agent": lambda state, node: {"done": True}})
    manager.start(workflow, run_id="run_source")
    source = manager.latest_checkpoint("run_source")

    fork = manager.fork_from_checkpoint(source.checkpoint_id, new_run_id="run_fork", metadata={"reason": "try again"})

    assert fork.run_id == "run_fork"
    assert fork.workflow_state["run_id"] == "run_fork"
    assert fork.parent_checkpoint_id == source.checkpoint_id
    assert fork.metadata["forked_from_checkpoint_id"] == source.checkpoint_id
    assert fork.metadata["forked_from_run_id"] == "run_source"
    assert fork.metadata["reason"] == "try again"
    assert manager.latest_checkpoint("run_fork").checkpoint_id == fork.checkpoint_id


def test_workflow_run_manager_raises_for_missing_checkpoint():
    import pytest

    from cody.core.runtime import WorkflowRunManager, WorkflowRunManagerError

    manager = WorkflowRunManager()

    with pytest.raises(WorkflowRunManagerError, match="Checkpoint not found"):
        manager.get_checkpoint("missing")

    with pytest.raises(WorkflowRunManagerError, match="No checkpoint found"):
        manager.resume_latest(None, run_id="missing_run")


def test_workflow_run_manager_async_resume_latest():
    import asyncio

    from cody.core.runtime import Workflow, WorkflowNodeType, WorkflowRunManager

    workflow = (
        Workflow(name="managed_async", workflow_id="workflow_managed_async")
        .node("one", WorkflowNodeType.AGENT)
        .node("two", WorkflowNodeType.AGENT)
        .edge("one", "two")
        .compile()
    )
    calls = []

    async def handler(state, node):
        calls.append(node.node_id)
        return {node.node_id: True}

    async def run():
        from cody.core.runtime import AsyncWorkflowExecutionError

        manager = WorkflowRunManager(async_node_handlers={"agent": handler})
        try:
            await manager.start_async(workflow, run_id="run_managed_async", max_steps=1)
        except AsyncWorkflowExecutionError:
            pass
        else:
            raise AssertionError("expected max-step failure")
        resumed = await manager.resume_latest_async(workflow, run_id="run_managed_async")
        return resumed, manager

    resumed, manager = asyncio.run(run())

    assert resumed.completed_node_ids == ["one", "two"]
    assert calls == ["one", "two"]
    assert any(event.event_type.value == "workflow.resumed" for event in manager.events("run_managed_async"))


def test_in_memory_run_store_tracks_runs_and_steps():
    from cody.core.runtime import InMemoryRunStore, RunRecord, RunStatus, StepRecord, StepStatus, StepType

    store = InMemoryRunStore()
    run = store.save_run(RunRecord(task="registry", run_id="run_registry").transition(RunStatus.RUNNING))
    step = store.save_step(StepRecord(run_id=run.run_id, step_id="step_registry", step_type=StepType.SYSTEM).start())

    assert store.get_run("run_registry") == run
    assert store.list_runs(status=RunStatus.RUNNING) == [run]
    assert store.get_step("step_registry") == step
    assert store.list_steps("run_registry")[0].status == StepStatus.RUNNING


def test_sqlite_run_store_persists_runs_and_steps(tmp_path):
    from cody.core.runtime import RunRecord, RunStatus, SQLiteRunStore, StepRecord, StepType

    db_path = tmp_path / "runtime-registry.sqlite"
    store = SQLiteRunStore(db_path)
    run = store.save_run(RunRecord(task="durable", run_id="run_durable", workflow_id="workflow_durable"))
    step = store.save_step(StepRecord(run_id=run.run_id, step_id="step_durable", step_type=StepType.TOOL).complete())

    reopened = SQLiteRunStore(db_path)

    assert reopened.get_run("run_durable") == run
    assert reopened.list_runs(status=RunStatus.CREATED) == [run]
    assert reopened.get_step("step_durable") == step
    assert reopened.list_steps("run_durable") == [step]


def test_workflow_run_manager_records_run_status_transitions():
    import pytest

    from cody.core.runtime import RunStatus, Workflow, WorkflowExecutionError, WorkflowNodeType, WorkflowRunManager

    workflow = (
        Workflow(name="status", workflow_id="workflow_status")
        .node("one", WorkflowNodeType.AGENT)
        .node("two", WorkflowNodeType.AGENT)
        .edge("one", "two")
        .compile()
    )
    manager = WorkflowRunManager(node_handlers={"agent": lambda state, node: {node.node_id: True}})

    with pytest.raises(WorkflowExecutionError, match="max_steps"):
        manager.start(workflow, run_id="run_status", initial_data={"task": "track status"}, max_steps=1)
    assert manager.get_run("run_status").status == RunStatus.FAILED

    manager.resume_latest(workflow, run_id="run_status")
    run = manager.get_run("run_status")

    assert run.status == RunStatus.COMPLETED
    assert run.task == "track status"
    assert run.workflow_id == "workflow_status"
    assert run.completed_at is not None


def test_workflow_run_manager_records_forked_run():
    from cody.core.runtime import RunStatus, Workflow, WorkflowNodeType, WorkflowRunManager

    workflow = Workflow(name="fork registry", workflow_id="workflow_fork_registry").node("start", WorkflowNodeType.AGENT).compile()
    manager = WorkflowRunManager(node_handlers={"agent": lambda state, node: {"done": True}})
    manager.start(workflow, run_id="run_fork_registry")
    checkpoint = manager.latest_checkpoint("run_fork_registry")

    manager.fork_from_checkpoint(checkpoint.checkpoint_id, new_run_id="run_fork_registry_child", metadata={"task": "child task"})
    child = manager.get_run("run_fork_registry_child")

    assert child.status == RunStatus.PAUSED
    assert child.parent_run_id == "run_fork_registry"
    assert child.workflow_id == "workflow_fork_registry"
    assert child.task == "child task"


def test_workflow_executor_records_completed_step_records():
    from cody.core.runtime import InMemoryRunStore, StepStatus, StepType, Workflow, WorkflowExecutor, WorkflowNodeType

    run_store = InMemoryRunStore()
    workflow = Workflow(name="steps", workflow_id="workflow_steps").node("agent", WorkflowNodeType.AGENT).compile()
    executor = WorkflowExecutor(
        run_store=run_store,
        node_handlers={"agent": lambda state, node: {"ok": True}},
    )

    executor.run(workflow, run_id="run_steps")
    steps = run_store.list_steps("run_steps")

    assert len(steps) == 1
    assert steps[0].step_id == "node_agent"
    assert steps[0].step_type == StepType.MODEL
    assert steps[0].status == StepStatus.COMPLETED
    assert steps[0].checkpoint_id is not None


def test_workflow_executor_records_failed_step_records():
    import pytest

    from cody.core.runtime import InMemoryRunStore, StepStatus, Workflow, WorkflowExecutor, WorkflowNodeType

    def fail(state, node):
        raise RuntimeError("boom")

    run_store = InMemoryRunStore()
    workflow = Workflow(name="failed_steps", workflow_id="workflow_failed_steps").node("agent", WorkflowNodeType.AGENT).compile()
    executor = WorkflowExecutor(run_store=run_store, node_handlers={"agent": fail})

    with pytest.raises(RuntimeError, match="boom"):
        executor.run(workflow, run_id="run_failed_steps")

    steps = run_store.list_steps("run_failed_steps")
    assert len(steps) == 1
    assert steps[0].status == StepStatus.FAILED
    assert steps[0].error_ref == "boom"


def test_async_workflow_executor_records_completed_step_records():
    import asyncio

    from cody.core.runtime import AsyncWorkflowExecutor, InMemoryRunStore, StepStatus, StepType, Workflow, WorkflowNodeType

    async def handler(state, node):
        return {"ok": True}

    async def run():
        run_store = InMemoryRunStore()
        workflow = Workflow(name="async_steps", workflow_id="workflow_async_steps").node("tool", WorkflowNodeType.TOOL).compile()
        executor = AsyncWorkflowExecutor(run_store=run_store, node_handlers={"tool": handler})
        await executor.run(workflow, run_id="run_async_steps")
        return run_store.list_steps("run_async_steps")

    steps = asyncio.run(run())

    assert len(steps) == 1
    assert steps[0].step_type == StepType.TOOL
    assert steps[0].status == StepStatus.COMPLETED
    assert steps[0].checkpoint_id is not None


def test_workflow_run_manager_pauses_without_marking_run_failed():
    import pytest

    from cody.core.runtime import RunStatus, Workflow, WorkflowNodeType, WorkflowPaused, WorkflowRunManager

    workflow = (
        Workflow(name="pausable", workflow_id="workflow_pausable")
        .node("one", WorkflowNodeType.AGENT)
        .node("two", WorkflowNodeType.AGENT)
        .edge("one", "two")
        .compile()
    )
    manager = WorkflowRunManager(node_handlers={"agent": lambda state, node: {node.node_id: True}})
    manager.request_pause("run_pause", before_node_id="two")

    with pytest.raises(WorkflowPaused, match="two"):
        manager.start(workflow, run_id="run_pause")

    assert manager.get_run("run_pause").status == RunStatus.PAUSED
    assert any(event.event_type.value == "workflow.paused" for event in manager.events("run_pause"))
    assert not any(event.event_type.value == "workflow.failed" for event in manager.events("run_pause"))

    manager.clear_pause("run_pause")
    resumed = manager.resume_latest(workflow, run_id="run_pause")

    assert resumed.completed_node_ids == ["one", "two"]
    assert manager.get_run("run_pause").status == RunStatus.COMPLETED


def test_workflow_run_manager_cancels_without_marking_run_failed():
    import pytest

    from cody.core.runtime import RunStatus, Workflow, WorkflowCancelled, WorkflowNodeType, WorkflowRunManager

    workflow = Workflow(name="cancelable", workflow_id="workflow_cancelable").node("one", WorkflowNodeType.AGENT).compile()
    manager = WorkflowRunManager(node_handlers={"agent": lambda state, node: {"should_not_run": True}})
    manager.request_cancel("run_cancel")

    with pytest.raises(WorkflowCancelled):
        manager.start(workflow, run_id="run_cancel")

    assert manager.get_run("run_cancel").status == RunStatus.CANCELLED
    assert any(event.event_type.value == "workflow.cancelled" for event in manager.events("run_cancel"))
    assert not any(event.event_type.value == "workflow.failed" for event in manager.events("run_cancel"))


def test_async_workflow_run_manager_pauses_at_node_boundary():
    import asyncio
    import pytest

    from cody.core.runtime import RunStatus, Workflow, WorkflowNodeType, WorkflowPaused, WorkflowRunManager

    async def handler(state, node):
        return {node.node_id: True}

    async def run():
        workflow = (
            Workflow(name="async_pausable", workflow_id="workflow_async_pausable")
            .node("one", WorkflowNodeType.AGENT)
            .node("two", WorkflowNodeType.AGENT)
            .edge("one", "two")
            .compile()
        )
        manager = WorkflowRunManager(async_node_handlers={"agent": handler})
        manager.request_pause("run_async_pause", before_node_id="two")
        with pytest.raises(WorkflowPaused):
            await manager.start_async(workflow, run_id="run_async_pause")
        return manager

    manager = asyncio.run(run())

    assert manager.get_run("run_async_pause").status == RunStatus.PAUSED
    assert any(event.event_type.value == "workflow.paused" for event in manager.events("run_async_pause"))


def test_in_memory_approval_store_tracks_pending_and_approved_requests():
    from cody.core.runtime import ApprovalRequestRecord, ApprovalStatus, InMemoryApprovalStore

    store = InMemoryApprovalStore()
    approval = store.save(ApprovalRequestRecord(
        run_id="run_approval",
        node_id="approve",
        request={"action": "merge"},
    ))
    approved = store.save(approval.approve({"approved": True, "by": "lead"}))

    assert store.get(approval.approval_id) == approved
    assert store.list(run_id="run_approval") == [approved]
    assert store.list(status=ApprovalStatus.APPROVED) == [approved]


def test_sqlite_approval_store_persists_requests(tmp_path):
    from cody.core.runtime import ApprovalRequestRecord, ApprovalStatus, SQLiteApprovalStore

    db_path = tmp_path / "approvals.sqlite"
    store = SQLiteApprovalStore(db_path)
    approval = store.save(ApprovalRequestRecord(
        run_id="run_sqlite_approval",
        node_id="approve",
        request={"action": "deploy"},
    ))
    store.save(approval.reject({"approved": False, "reason": "needs tests"}))

    reopened = SQLiteApprovalStore(db_path)

    assert reopened.get(approval.approval_id).status == ApprovalStatus.REJECTED
    assert reopened.list(run_id="run_sqlite_approval")[0].response["reason"] == "needs tests"


def test_queued_human_approval_node_waits_and_records_request():
    import pytest

    from cody.core.runtime import (
        ApprovalStatus,
        InMemoryApprovalStore,
        InMemoryRunStore,
        RunStatus,
        StepStatus,
        Workflow,
        WorkflowNodeType,
        WorkflowRunManager,
        WorkflowWaiting,
        queued_human_approval_node_handler,
    )

    approval_store = InMemoryApprovalStore()
    run_store = InMemoryRunStore()
    workflow = (
        Workflow(name="approval_wait", workflow_id="workflow_approval_wait")
        .node("approval", WorkflowNodeType.HUMAN_APPROVAL, metadata={"request": {"action": "ship"}})
        .compile()
    )
    manager = WorkflowRunManager(
        node_handlers={"human_approval": queued_human_approval_node_handler(approval_store)},
        run_store=run_store,
    )

    with pytest.raises(WorkflowWaiting, match="approval_"):
        manager.start(workflow, run_id="run_waiting_approval")

    approvals = approval_store.list(run_id="run_waiting_approval")
    steps = run_store.list_steps("run_waiting_approval")

    assert manager.get_run("run_waiting_approval").status == RunStatus.WAITING
    assert approvals[0].status == ApprovalStatus.PENDING
    assert approvals[0].request == {"action": "ship"}
    assert steps[0].status == StepStatus.WAITING
    assert any(event.event_type.value == "workflow.waiting" for event in manager.events("run_waiting_approval"))


def test_queued_human_approval_resumes_after_approval_without_duplicate_request():
    import pytest

    from cody.core.runtime import (
        ApprovalStatus,
        InMemoryApprovalStore,
        InMemoryRunStore,
        RunStatus,
        Workflow,
        WorkflowNodeType,
        WorkflowRunManager,
        WorkflowWaiting,
        queued_human_approval_node_handler,
    )

    approval_store = InMemoryApprovalStore()
    run_store = InMemoryRunStore()
    workflow = (
        Workflow(name="approval_resume", workflow_id="workflow_approval_resume")
        .node("approval", WorkflowNodeType.HUMAN_APPROVAL, metadata={"request": {"action": "ship"}})
        .compile()
    )
    manager = WorkflowRunManager(
        node_handlers={"human_approval": queued_human_approval_node_handler(approval_store)},
        run_store=run_store,
    )

    with pytest.raises(WorkflowWaiting):
        manager.start(workflow, run_id="run_approval_resume")
    approval = approval_store.list(run_id="run_approval_resume")[0]
    approval_store.approve(approval.approval_id, {"approved": True, "approved_by": "lead"})

    state = manager.resume_latest(workflow, run_id="run_approval_resume")

    approvals = approval_store.list(run_id="run_approval_resume")
    assert len(approvals) == 1
    assert approvals[0].status == ApprovalStatus.APPROVED
    assert manager.get_run("run_approval_resume").status == RunStatus.COMPLETED
    assert state.data["approved"] is True
    assert state.data["approved_by"] == "lead"


def test_queued_human_approval_resumes_after_rejection():
    import pytest

    from cody.core.runtime import InMemoryApprovalStore, Workflow, WorkflowNodeType, WorkflowRunManager, WorkflowWaiting, queued_human_approval_node_handler

    approval_store = InMemoryApprovalStore()
    workflow = Workflow(name="approval_reject", workflow_id="workflow_approval_reject").node(
        "approval",
        WorkflowNodeType.HUMAN_APPROVAL,
        metadata={"request": {"action": "ship"}},
    ).compile()
    manager = WorkflowRunManager(node_handlers={"human_approval": queued_human_approval_node_handler(approval_store)})

    with pytest.raises(WorkflowWaiting):
        manager.start(workflow, run_id="run_approval_reject")
    approval = approval_store.list(run_id="run_approval_reject")[0]
    approval_store.reject(approval.approval_id, {"reason": "needs tests"})

    state = manager.resume_latest(workflow, run_id="run_approval_reject")

    assert state.data["approved"] is False
    assert state.data["reason"] == "needs tests"


def test_artifact_record_round_trip():
    from cody.core.runtime import ArtifactRecord, ArtifactType

    artifact = ArtifactRecord(
        run_id="run_artifact",
        step_id="node_plan",
        checkpoint_id="ckpt_plan",
        event_id="event_plan",
        artifact_type=ArtifactType.PLAN,
        name="plan",
        content={"steps": ["one", "two"]},
        metadata={"source": "planner"},
    )

    assert ArtifactRecord.from_dict(artifact.to_dict()) == artifact


def test_in_memory_artifact_store_filters_by_run_step_and_type():
    from cody.core.runtime import ArtifactRecord, ArtifactType, InMemoryArtifactStore

    store = InMemoryArtifactStore()
    plan = store.save(ArtifactRecord(
        run_id="run_artifacts",
        step_id="node_plan",
        artifact_type=ArtifactType.PLAN,
        content={"plan": "ship"},
    ))
    diff = store.save(ArtifactRecord(
        run_id="run_artifacts",
        step_id="node_code",
        artifact_type=ArtifactType.DIFF,
        content="diff --git a/app.py b/app.py",
    ))

    assert store.get(plan.artifact_id) == plan
    assert store.list(run_id="run_artifacts") == [plan, diff]
    assert store.list(step_id="node_code") == [diff]
    assert store.list(run_id="run_artifacts", artifact_type=ArtifactType.PLAN) == [plan]


def test_sqlite_artifact_store_persists_artifacts(tmp_path):
    from cody.core.runtime import ArtifactRecord, ArtifactType, SQLiteArtifactStore

    db_path = tmp_path / "artifacts.sqlite"
    store = SQLiteArtifactStore(db_path)
    report = store.save(ArtifactRecord(
        run_id="run_artifact_sqlite",
        step_id="node_test",
        artifact_type=ArtifactType.TEST_REPORT,
        content={"passed": True},
        name="pytest report",
    ))

    reopened = SQLiteArtifactStore(db_path)

    assert reopened.get(report.artifact_id) == report
    assert reopened.list(run_id="run_artifact_sqlite", artifact_type=ArtifactType.TEST_REPORT) == [report]
    assert reopened.list(step_id="node_test") == [report]


def test_registry_tool_backend_executes_and_writes_artifact():
    from cody.core.runtime import (
        ArtifactType,
        InMemoryArtifactStore,
        ToolPolicy,
        ToolRegistry,
        ToolSpec,
        WorkflowNode,
        WorkflowNodeType,
        WorkflowState,
        registry_tool_backend,
    )

    registry = ToolRegistry()
    registry.register(ToolSpec(
        name="pytest",
        handler=lambda args, state, node: {"tests_passed": True, "command": args["command"]},
        required_args=("command",),
        capabilities=("exec",),
        artifact_type=ArtifactType.TEST_REPORT,
    ))
    artifact_store = InMemoryArtifactStore()
    backend = registry_tool_backend(
        registry,
        policy=ToolPolicy(allowed_tools=frozenset({"pytest"}), allowed_capabilities=frozenset({"exec"})),
        artifact_store=artifact_store,
    )
    state = WorkflowState(workflow_id="workflow_tools", run_id="run_tools")
    node = WorkflowNode(node_id="test", node_type=WorkflowNodeType.TOOL, tool_name="pytest")

    output = backend("pytest", {"command": "pytest"}, state, node)

    artifacts = artifact_store.list(run_id="run_tools", artifact_type=ArtifactType.TEST_REPORT)
    assert output["tests_passed"] is True
    assert output["artifact_id"] == artifacts[0].artifact_id
    assert artifacts[0].content["command"] == "pytest"


def test_registry_tool_backend_enforces_policy_and_args():
    import pytest

    from cody.core.runtime import ToolExecutionDenied, ToolPolicy, ToolRegistry, ToolSpec, WorkflowNode, WorkflowNodeType, WorkflowState, registry_tool_backend

    registry = ToolRegistry()
    registry.register(ToolSpec(
        name="write_file",
        handler=lambda args, state, node: {"written": args["path"]},
        required_args=("path",),
        capabilities=("write",),
    ))
    state = WorkflowState(workflow_id="workflow_policy", run_id="run_policy")
    node = WorkflowNode(node_id="write", node_type=WorkflowNodeType.TOOL, tool_name="write_file")

    denied_backend = registry_tool_backend(registry, policy=ToolPolicy(denied_tools=frozenset({"write_file"})))
    with pytest.raises(ToolExecutionDenied, match="denied"):
        denied_backend("write_file", {"path": "README.md"}, state, node)

    allowed_backend = registry_tool_backend(registry, policy=ToolPolicy(allowed_capabilities=frozenset({"write"})))
    with pytest.raises(ValueError, match="missing required args"):
        allowed_backend("write_file", {}, state, node)

    with pytest.raises(KeyError, match="not registered"):
        allowed_backend("missing", {}, state, node)


def test_workflow_scheduler_parallel_join_fan_in():
    from cody.core.runtime import Workflow, WorkflowEdgeType, WorkflowNodeType, WorkflowScheduler

    workflow = (
        Workflow(name="parallel join")
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
    order: list[str] = []

    def handler(state, node):
        order.append(node.node_id)
        return {node.node_id: True}

    scheduler = WorkflowScheduler(node_handlers={"function": handler})
    state = scheduler.run(workflow, run_id="run_parallel")

    assert state.current_node_id is None
    assert order[:3] == ["start", "left", "right"]
    assert order[-1] == "join"
    assert state.completed_node_ids == ["start", "left", "right", "join"]
    assert state.data["left"] is True
    assert state.data["right"] is True


def test_workflow_scheduler_fallback_edge_recovers_from_handler_failure():
    from cody.core.runtime import Workflow, WorkflowEdgeType, WorkflowNodeType, WorkflowScheduler

    workflow = (
        Workflow(name="fallback")
        .node("primary", WorkflowNodeType.FUNCTION)
        .node("fallback", WorkflowNodeType.FUNCTION)
        .edge("primary", "fallback", edge_type=WorkflowEdgeType.FALLBACK)
        .compile()
    )

    def primary(_state, node):
        if node.node_id == "primary":
            raise RuntimeError("boom")
        return {"recovered": True}

    scheduler = WorkflowScheduler(node_handlers={"function": primary})
    state = scheduler.run(workflow, run_id="run_fallback")

    assert state.failed_node_ids == ["primary"]
    assert state.completed_node_ids == ["fallback"]
    assert state.data["recovered"] is True


def test_workflow_scheduler_nested_workflow_records_child_run():
    from cody.core.runtime import Workflow, WorkflowNodeType, WorkflowScheduler

    child = (
        Workflow(name="child", workflow_id="child_flow")
        .node("child_step", WorkflowNodeType.FUNCTION)
        .compile()
    )
    parent = (
        Workflow(name="parent")
        .node("nested", WorkflowNodeType.NESTED_WORKFLOW, metadata={"workflow_id": "child_flow"})
        .compile()
    )

    def child_handler(_state, node):
        return {node.node_id: "done"}

    scheduler = WorkflowScheduler(
        node_handlers={"function": child_handler},
        nested_workflows={"child_flow": child},
    )
    state = scheduler.run(parent, run_id="run_parent")

    assert state.completed_node_ids == ["nested"]
    assert state.data["child_run_ids"] == ["run_parent_nested"]
    assert state.data["nested_result"]["child_step"] == "done"
    child_checkpoints = scheduler.checkpoint_store.list_checkpoints("run_parent_nested")
    assert child_checkpoints


def test_multi_agent_coordinator_runs_dependencies_and_reducer():
    from cody.core.runtime import AgentRole, AgentTask, MultiAgentCoordinator, WorkflowState

    calls: list[str] = []

    def researcher(task, state):
        calls.append(task.task_id)
        return {"notes": f"researched {state.data['topic']}"}

    def reviewer(task, state):
        calls.append(task.task_id)
        return {"review": state.data["agent_outputs"]["research"]["notes"].upper()}

    coordinator = MultiAgentCoordinator(
        reducer=lambda records, _state: {"final": [record.task.task_id for record in records]},
    )
    coordinator.register_agent(AgentRole("researcher", capabilities=frozenset({"research"})), researcher)
    coordinator.register_agent(AgentRole("reviewer", capabilities=frozenset({"review"})), reviewer)
    state = WorkflowState(workflow_id="wf", run_id="run_agents", data={"topic": "runtime"})
    tasks = [
        AgentTask.create("research", task_id="research", required_capabilities={"research"}),
        AgentTask.create("review", task_id="review", required_capabilities={"review"}, depends_on=("research",)),
    ]

    final_state, records = coordinator.run(tasks, state=state)

    assert calls == ["research", "review"]
    assert [record.status.value for record in records] == ["completed", "completed"]
    assert final_state.data["agent_outputs"]["review"]["review"] == "RESEARCHED RUNTIME"
    assert final_state.data["final"] == ["research", "review"]
    assert coordinator.trace_store.list_events(run_id="run_agents")


def test_multi_agent_coordinator_fallback_and_artifacts():
    from cody.core.runtime import AgentRole, AgentTask, InMemoryArtifactStore, MultiAgentCoordinator, WorkflowState

    artifact_store = InMemoryArtifactStore()
    coordinator = MultiAgentCoordinator(artifact_store=artifact_store)

    def broken(_task, _state):
        raise RuntimeError("primary failed")

    def fallback(task, _state):
        return {"task": task.prompt, "ok": True}

    coordinator.register_agent(AgentRole("primary", capabilities=frozenset({"code"})), broken)
    coordinator.register_agent(AgentRole("fallback", capabilities=frozenset({"code"})), fallback)
    state = WorkflowState(workflow_id="wf", run_id="run_fallback_agents")
    task = AgentTask.create(
        "implement",
        task_id="code",
        required_capabilities={"code"},
        preferred_agent_id="primary",
        fallback_agent_ids=("fallback",),
    )

    final_state, records = coordinator.run([task], state=state)

    assert records[0].status.value == "completed"
    assert records[0].assigned_agent_id == "fallback"
    assert final_state.data["agent_outputs"]["code"]["ok"] is True
    artifacts = artifact_store.list(run_id="run_fallback_agents")
    assert len(artifacts) == 1
    assert artifacts[0].content["ok"] is True


def test_multi_agent_coordinator_skips_failed_dependency():
    from cody.core.runtime import AgentRole, AgentTask, MultiAgentCoordinator, WorkflowState

    coordinator = MultiAgentCoordinator()
    coordinator.register_agent(AgentRole("worker", capabilities=frozenset({"work"})), lambda _task, _state: (_ for _ in ()).throw(RuntimeError("boom")))
    state = WorkflowState(workflow_id="wf", run_id="run_skip")
    tasks = [
        AgentTask.create("first", task_id="first", required_capabilities={"work"}),
        AgentTask.create("second", task_id="second", required_capabilities={"work"}, depends_on=("first",)),
    ]

    _state, records = coordinator.run(tasks, state=state)

    assert records[0].status.value == "failed"
    assert records[1].status.value == "skipped"
    assert "Dependency failed" in records[1].error


def test_quality_gate_runner_scores_and_persists_decision():
    from cody.core.runtime import (
        EvaluationMetric,
        InMemoryArtifactStore,
        QualityGate,
        QualityGateRunner,
        QualityGateStatus,
        WorkflowState,
    )

    artifact_store = InMemoryArtifactStore()
    runner = QualityGateRunner(
        artifact_store=artifact_store,
        evaluators={
            "tests": lambda state, _metric: {"score": 1.0 if state.data["tests_passed"] else 0.0, "name": "tests"},
            "review": lambda state, _metric: state.data["review_score"],
        },
    )
    gate = QualityGate.create(
        gate_id="ship_gate",
        min_score=0.8,
        metrics=[
            EvaluationMetric("tests", threshold=1.0, weight=2.0, required=True),
            EvaluationMetric("review", threshold=0.7, weight=1.0, required=False),
        ],
    )
    state = WorkflowState(workflow_id="wf", run_id="run_quality", data={"tests_passed": True, "review_score": 0.8})

    decision = runner.evaluate(gate, state)

    assert decision.status == QualityGateStatus.PASSED
    assert decision.passed is True
    assert decision.score >= 0.9
    assert decision.artifact_id is not None
    assert artifact_store.get(decision.artifact_id).content["status"] == "passed"
    assert runner.trace_store.list_events(run_id="run_quality")
    assert runner.checkpoint_store.latest("run_quality").artifact_refs == [decision.artifact_id]


def test_quality_gate_runner_blocks_required_failures():
    from cody.core.runtime import EvaluationMetric, QualityGate, QualityGateRunner, QualityGateStatus, WorkflowState

    runner = QualityGateRunner(evaluators={"tests": lambda _state, _metric: False})
    gate = QualityGate.create(
        [EvaluationMetric("tests", threshold=1.0, required=True)],
        gate_id="required_gate",
        min_score=0.1,
    )
    state = WorkflowState(workflow_id="wf", run_id="run_quality_fail")

    decision = runner.evaluate(gate, state)

    assert decision.status == QualityGateStatus.FAILED
    assert decision.blocking_failures == ("tests",)
    with pytest.raises(RuntimeError, match="Quality gate failed"):
        runner.assert_passed(gate, state)


def test_quality_gate_runner_warns_for_non_required_metric_failure():
    from cody.core.runtime import EvaluationMetric, QualityGate, QualityGateRunner, QualityGateStatus, WorkflowState

    runner = QualityGateRunner(evaluators={"lint": lambda _state, _metric: 0.4, "tests": lambda _state, _metric: 1.0})
    gate = QualityGate.create(
        [
            EvaluationMetric("tests", threshold=1.0, required=True),
            EvaluationMetric("lint", threshold=0.8, required=False),
        ],
        gate_id="warning_gate",
        min_score=0.6,
        artifact_outputs=False,
    )
    state = WorkflowState(workflow_id="wf", run_id="run_quality_warn")

    decision = runner.evaluate(gate, state)

    assert decision.status == QualityGateStatus.WARNING
    assert decision.artifact_id is None
    assert decision.blocking_failures == ()


def test_timeline_api_links_events_checkpoints_and_artifacts():
    from cody.core.runtime import (
        ArtifactRecord,
        ArtifactType,
        CheckpointRecord,
        InMemoryArtifactStore,
        InMemoryCheckpointStore,
        InMemoryTraceStore,
        RunEvent,
        RunEventType,
        TimelineAPI,
    )

    trace_store = InMemoryTraceStore()
    checkpoint_store = InMemoryCheckpointStore()
    artifact_store = InMemoryArtifactStore()
    artifact = artifact_store.save(
        ArtifactRecord(
            run_id="run_timeline",
            step_id="step_1",
            artifact_type=ArtifactType.REVIEW,
            content={"score": 1.0},
        )
    )
    checkpoint = checkpoint_store.save(
        CheckpointRecord(
            run_id="run_timeline",
            step_id="step_1",
            workflow_state={"current_node_id": "review"},
            artifact_refs=[artifact.artifact_id],
        )
    )
    event = trace_store.append(
        RunEvent(
            event_type=RunEventType.WORKFLOW_NODE_COMPLETED,
            run_id="run_timeline",
            step_id="step_1",
            payload={"checkpoint_id": checkpoint.checkpoint_id},
        )
    )

    api = TimelineAPI(trace_store=trace_store, checkpoint_store=checkpoint_store, artifact_store=artifact_store)
    timeline = api.timeline("run_timeline")

    assert len(timeline.items) == 1
    assert timeline.items[0].event.event_id == event.event_id
    assert timeline.items[0].checkpoint.checkpoint_id == checkpoint.checkpoint_id
    assert timeline.items[0].artifacts[0].artifact_id == artifact.artifact_id
    assert timeline.filter(event_type=RunEventType.WORKFLOW_NODE_COMPLETED.value).items
    assert timeline.filter(step_id="missing").items == ()


def test_timeline_api_frame_replay_and_export():
    from cody.core.runtime import InMemoryTraceStore, RunEvent, RunEventType, TimelineAPI

    trace_store = InMemoryTraceStore()
    first = trace_store.append(RunEvent(event_type=RunEventType.WORKFLOW_STARTED, run_id="run_replay", step_id="start"))
    second = trace_store.append(RunEvent(event_type=RunEventType.WORKFLOW_COMPLETED, run_id="run_replay", step_id="done"))
    api = TimelineAPI(trace_store=trace_store)

    frame = api.frame("run_replay", 1)
    replay = api.replay("run_replay", until_index=0)
    exported = api.export("run_replay")

    assert frame.event_id == second.event_id
    assert frame.event_type == RunEventType.WORKFLOW_COMPLETED.value
    assert replay == [first.to_dict()]
    assert exported["items"][1]["event"]["event_id"] == second.event_id
    with pytest.raises(IndexError, match="Timeline index out of range"):
        api.frame("run_replay", 99)


def test_runtime_interface_exposes_runs_timeline_frame_and_replay():
    from cody.core.runtime import InMemoryRunStore, InMemoryTraceStore, RunEvent, RunEventType, RunRecord, RuntimeInterface

    trace_store = InMemoryTraceStore()
    run_store = InMemoryRunStore()
    run_store.save_run(RunRecord(run_id="run_ui", task="Inspect UI", workflow_id="wf"))
    first = trace_store.append(RunEvent(event_type=RunEventType.WORKFLOW_STARTED, run_id="run_ui", step_id="start"))
    trace_store.append(RunEvent(event_type=RunEventType.WORKFLOW_COMPLETED, run_id="run_ui", step_id="done"))
    interface = RuntimeInterface(trace_store=trace_store, run_store=run_store)

    runs = interface.handle("runs.list")
    timeline = interface.handle("timeline.get", run_id="run_ui")
    frame = interface.handle("timeline.frame", run_id="run_ui", index=1)
    replay = interface.handle("timeline.replay", run_id="run_ui", until_index=0)

    assert runs.ok is True
    assert runs.data["runs"][0]["run_id"] == "run_ui"
    assert timeline.data["items"][0]["event"]["event_id"] == first.event_id
    assert frame.data["event_type"] == RunEventType.WORKFLOW_COMPLETED.value
    assert replay.data["events"] == [first.to_dict()]


def test_runtime_interface_approval_and_artifact_actions():
    from cody.core.runtime import (
        ApprovalRequestRecord,
        ArtifactType,
        InMemoryApprovalStore,
        InMemoryArtifactStore,
        InMemoryTraceStore,
        RuntimeInterface,
    )

    approval_store = InMemoryApprovalStore()
    approval = approval_store.save(ApprovalRequestRecord(run_id="run_ui", node_id="approve", request={"text": "ship?"}))
    artifact_store = InMemoryArtifactStore()
    interface = RuntimeInterface(
        trace_store=InMemoryTraceStore(),
        approval_store=approval_store,
        artifact_store=artifact_store,
    )

    pending = interface.handle("approvals.list", run_id="run_ui", status="pending")
    approved = interface.handle("approvals.approve", approval_id=approval.approval_id, response={"approved": True})
    saved = interface.handle(
        "artifacts.save",
        run_id="run_ui",
        step_id="step_ui",
        artifact_type=ArtifactType.REVIEW.value,
        name="review.json",
        content={"ok": True},
    )
    artifacts = interface.handle("artifacts.list", run_id="run_ui")

    assert pending.ok is True
    assert pending.data["approvals"][0]["approval_id"] == approval.approval_id
    assert approved.data["approval"]["status"] == "approved"
    assert saved.data["artifact"]["artifact_type"] == ArtifactType.REVIEW.value
    assert artifacts.data["artifacts"][0]["name"] == "review.json"
    assert interface.handle("unknown.action").ok is False


def test_runtime_interface_reports_missing_optional_stores():
    from cody.core.runtime import InMemoryTraceStore, RuntimeInterface

    interface = RuntimeInterface(trace_store=InMemoryTraceStore())

    assert interface.handle("approvals.list").error == "Approval store is not configured"
    assert interface.handle("artifacts.list").error == "Artifact store is not configured"


def test_runtime_command_router_dispatches_cli_args():
    from cody.core.runtime import InMemoryArtifactStore, InMemoryTraceStore, RuntimeCommandRouter, RuntimeInterface

    interface = RuntimeInterface(trace_store=InMemoryTraceStore(), artifact_store=InMemoryArtifactStore())
    router = RuntimeCommandRouter(interface)

    saved = router.run([
        "artifacts.save",
        "run-id=run_cli",
        "step-id=step_cli",
        "content={\"ok\":true}",
        "name=cli.json",
    ])
    listed = router.run(["artifacts.list", "run-id=run_cli"])

    assert saved.ok is True
    assert saved.data["artifact"]["content"] == {"ok": True}
    assert listed.data["artifacts"][0]["name"] == "cli.json"
    with pytest.raises(ValueError, match="key=value"):
        router.run(["runs.list", "badarg"])
    assert router.run([]).error == "Missing runtime action"


def test_runtime_web_router_returns_json_ready_dicts():
    from cody.core.runtime import InMemoryTraceStore, RunEvent, RunEventType, RuntimeActionRequest, RuntimeInterface, RuntimeWebRouter

    trace_store = InMemoryTraceStore()
    trace_store.append(RunEvent(event_type=RunEventType.WORKFLOW_STARTED, run_id="run_web", step_id="start"))
    router = RuntimeWebRouter(RuntimeInterface(trace_store=trace_store))

    response = router.handle(RuntimeActionRequest(action="timeline.get", params={"run_id": "run_web"}, actor_id="user_1"))
    dict_response = router.handle({"action": "timeline.replay", "params": {"run_id": "run_web"}})

    assert response["ok"] is True
    assert response["data"]["actor_id"] == "user_1"
    assert response["data"]["items"][0]["event"]["step_id"] == "start"
    assert dict_response["data"]["events"][0]["step_id"] == "start"


def test_runtime_tui_view_builds_dashboard_and_run_detail():
    from cody.core.runtime import (
        ApprovalRequestRecord,
        ArtifactRecord,
        ArtifactType,
        InMemoryApprovalStore,
        InMemoryArtifactStore,
        InMemoryTraceStore,
        RunEvent,
        RunEventType,
        RuntimeInterface,
        RuntimeTUIView,
    )

    trace_store = InMemoryTraceStore()
    trace_store.append(RunEvent(event_type=RunEventType.WORKFLOW_STARTED, run_id="run_tui", step_id="start"))
    approval_store = InMemoryApprovalStore()
    approval_store.save(ApprovalRequestRecord(run_id="run_tui", node_id="approve", request={"title": "Ship?"}))
    artifact_store = InMemoryArtifactStore()
    artifact_store.save(ArtifactRecord(run_id="run_tui", step_id="start", artifact_type=ArtifactType.REVIEW, content={"ok": True}))
    view = RuntimeTUIView(RuntimeInterface(trace_store=trace_store, approval_store=approval_store, artifact_store=artifact_store))

    dashboard = view.dashboard()
    detail = view.run_detail("run_tui")

    assert dashboard["runs"] == [{"run_id": "run_tui"}]
    assert dashboard["pending_approvals"][0]["node_id"] == "approve"
    assert detail["timeline"][0]["event"]["step_id"] == "start"
    assert detail["artifacts"][0]["content"] == {"ok": True}


def test_runtime_action_policy_blocks_mutations_without_actor():
    from cody.core.runtime import InMemoryArtifactStore, InMemoryTraceStore, RuntimeActionPolicy, RuntimeInterface

    interface = RuntimeInterface(
        trace_store=InMemoryTraceStore(),
        artifact_store=InMemoryArtifactStore(),
        action_policy=RuntimeActionPolicy(),
    )

    denied = interface.handle("artifacts.save", run_id="run_sec", content={"ok": True})
    allowed = interface.handle("artifacts.save", actor_id="user_1", run_id="run_sec", content={"ok": True})

    assert denied.ok is False
    assert denied.error == "Action requires actor_id: artifacts.save"
    assert allowed.ok is True


def test_runtime_action_policy_allowlists_denies_and_actor_scopes():
    from cody.core.runtime import InMemoryTraceStore, RuntimeActionPolicy, RuntimeInterface

    policy = RuntimeActionPolicy(
        allowed_actions=frozenset({"runs.list", "timeline.get"}),
        denied_actions=frozenset({"timeline.get"}),
        actor_allowed_actions={"viewer": frozenset({"runs.list"})},
    )
    interface = RuntimeInterface(trace_store=InMemoryTraceStore(), action_policy=policy)

    assert interface.handle("timeline.get", actor_id="viewer", run_id="run_sec").error == "Action is denied: timeline.get"
    assert interface.handle("timeline.replay", actor_id="viewer", run_id="run_sec").error == "Action is not allowlisted: timeline.replay"
    assert interface.handle("runs.list", actor_id="viewer").ok is True
    assert interface.handle("runs.list", actor_id="blocked").ok is True


def test_runtime_presentation_passes_actor_id_to_policy():
    from cody.core.runtime import InMemoryArtifactStore, InMemoryTraceStore, RuntimeActionPolicy, RuntimeCommandRouter, RuntimeInterface, RuntimeWebRouter

    interface = RuntimeInterface(
        trace_store=InMemoryTraceStore(),
        artifact_store=InMemoryArtifactStore(),
        action_policy=RuntimeActionPolicy(),
    )
    cli = RuntimeCommandRouter(interface)
    web = RuntimeWebRouter(interface)

    cli_denied = cli.run(["artifacts.save", "run-id=run_sec", "content={}"])
    cli_allowed = cli.run(["artifacts.save", "actor-id=user_cli", "run-id=run_sec", "content={}"])
    web_allowed = web.handle({"action": "artifacts.save", "actor_id": "user_web", "params": {"run_id": "run_sec", "content": {}}})

    assert cli_denied.ok is False
    assert cli_allowed.ok is True
    assert web_allowed["ok"] is True


def test_runtime_token_authority_issues_and_verifies_principal():
    from cody.core.runtime import RuntimeAuthError, RuntimePrincipal, RuntimeTokenAuthority

    authority = RuntimeTokenAuthority("secret")
    token = authority.issue(RuntimePrincipal("user_token", scopes=frozenset({"runtime:write"}), metadata={"team": "core"}))
    principal = authority.verify(token)

    assert principal.actor_id == "user_token"
    assert principal.scopes == frozenset({"runtime:write"})
    assert principal.metadata == {"team": "core"}
    with pytest.raises(RuntimeAuthError, match="signature"):
        RuntimeTokenAuthority("other").verify(token)
    with pytest.raises(RuntimeAuthError, match="format"):
        authority.verify("bad-token")


def test_runtime_web_router_uses_token_actor_for_authorization():
    from cody.core.runtime import (
        InMemoryArtifactStore,
        InMemoryTraceStore,
        RuntimeActionPolicy,
        RuntimeInterface,
        RuntimePrincipal,
        RuntimeTokenAuthority,
        RuntimeWebRouter,
    )

    authority = RuntimeTokenAuthority("secret")
    token = authority.issue(RuntimePrincipal("web_user"))
    interface = RuntimeInterface(
        trace_store=InMemoryTraceStore(),
        artifact_store=InMemoryArtifactStore(),
        action_policy=RuntimeActionPolicy(),
    )
    router = RuntimeWebRouter(interface, token_authority=authority)

    response = router.handle({
        "action": "artifacts.save",
        "token": token,
        "params": {"run_id": "run_token", "content": {"ok": True}},
    })
    denied = router.handle({
        "action": "artifacts.save",
        "token": token + "tampered",
        "params": {"run_id": "run_token", "content": {"ok": True}},
    })

    assert response["ok"] is True
    assert response["data"]["actor_id"] == "web_user"
    assert denied["ok"] is False
    assert "signature" in denied["error"]


def test_runtime_interface_writes_audit_records_for_allowed_and_denied_actions():
    from cody.core.runtime import (
        InMemoryArtifactStore,
        InMemoryRuntimeAuditStore,
        InMemoryTraceStore,
        RuntimeActionPolicy,
        RuntimeInterface,
    )

    audit_store = InMemoryRuntimeAuditStore()
    interface = RuntimeInterface(
        trace_store=InMemoryTraceStore(),
        artifact_store=InMemoryArtifactStore(),
        action_policy=RuntimeActionPolicy(),
        audit_store=audit_store,
    )

    denied = interface.handle("artifacts.save", run_id="run_audit", content={"secret": True})
    allowed = interface.handle("artifacts.save", actor_id="auditor", run_id="run_audit", content={"secret": True})
    unknown = interface.handle("missing.action", actor_id="auditor", run_id="run_audit")
    records = audit_store.list(action="artifacts.save")

    assert denied.ok is False
    assert allowed.ok is True
    assert len(records) == 2
    assert records[0].ok is False
    assert records[0].effect == "write"
    assert records[0].metadata["params"]["content"] == "<redacted>"
    assert records[1].actor_id == "auditor"
    assert audit_store.list(action="missing.action")[0].error == "Unknown runtime action: missing.action"
    assert unknown.ok is False


def test_sqlite_runtime_audit_store_persists_records(tmp_path):
    from cody.core.runtime import RuntimeAuditRecord, SQLiteRuntimeAuditStore

    db_path = tmp_path / "runtime-audit.sqlite3"
    store = SQLiteRuntimeAuditStore(db_path)
    store.append(RuntimeAuditRecord(action="runs.list", actor_id="reader", ok=True, effect="read"))
    store.append(RuntimeAuditRecord(action="artifacts.save", actor_id="writer", ok=False, effect="write", error="denied"))

    reopened = SQLiteRuntimeAuditStore(db_path)

    assert [record.action for record in reopened.list(actor_id="reader")] == ["runs.list"]
    failed = reopened.list(action="artifacts.save")[0]
    assert failed.actor_id == "writer"
    assert failed.error == "denied"


def test_runtime_store_bundle_in_memory_wires_interface_and_audit():
    from cody.core.runtime import RuntimeActionPolicy, RuntimeStoreBundle

    bundle = RuntimeStoreBundle.in_memory()
    interface = bundle.interface(action_policy=RuntimeActionPolicy())

    denied = interface.handle("artifacts.save", run_id="run_bundle", content={"secret": True})
    allowed = interface.handle("artifacts.save", actor_id="bundle_user", run_id="run_bundle", content={"ok": True})
    artifacts = interface.handle("artifacts.list", run_id="run_bundle")

    assert denied.ok is False
    assert allowed.ok is True
    assert artifacts.data["artifacts"][0]["content"] == {"ok": True}
    assert [record.action for record in bundle.audit_store.list(actor_id="bundle_user")] == ["artifacts.save"]


def test_runtime_store_bundle_sqlite_persists_across_reopen(tmp_path):
    from cody.core.runtime import RuntimeStoreBundle

    root = tmp_path / "runtime"
    bundle = RuntimeStoreBundle.sqlite(root)
    interface = bundle.interface()
    interface.handle("artifacts.save", run_id="run_sqlite_bundle", content={"ok": True})
    interface.handle("runs.list")

    reopened = RuntimeStoreBundle.sqlite(root)
    reopened_interface = reopened.interface()

    assert reopened_interface.handle("artifacts.list", run_id="run_sqlite_bundle").data["artifacts"][0]["content"] == {"ok": True}
    assert reopened.audit_store.list(action="runs.list")
