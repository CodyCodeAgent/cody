from cody.core.runner import CodyResult, DoneEvent, TextDeltaEvent, ToolCallEvent, ToolTrace
from cody.core.runtime import (
    InMemoryCheckpointStore,
    InMemoryTraceStore,
    RunEvent,
    RunEventType,
    stream_event_to_run_event,
)


def test_run_event_to_dict_uses_stable_envelope():
    event = RunEvent(
        event_type=RunEventType.RUN_STARTED,
        run_id="run_1",
        step_id="step_1",
        payload={"task": "refactor"},
    )

    data = event.to_dict()

    assert data["schema_version"] == "2026-07-03.v1"
    assert data["event_type"] == "run.started"
    assert data["run_id"] == "run_1"
    assert data["step_id"] == "step_1"
    assert data["payload"] == {"task": "refactor"}
    assert data["actor"] == {"kind": "runtime", "id": "cody"}
    assert data["event_id"]
    assert data["timestamp"].endswith("+00:00")


def test_trace_store_appends_and_filters_by_run_id():
    store = InMemoryTraceStore()
    run_a = RunEvent(RunEventType.RUN_STARTED, run_id="a")
    run_b = RunEvent(RunEventType.RUN_STARTED, run_id="b")
    run_a_done = RunEvent(RunEventType.RUN_COMPLETED, run_id="a")

    store.extend([run_a, run_b, run_a_done])

    assert store.list_events() == [run_a, run_b, run_a_done]
    assert store.list_events("a") == [run_a, run_a_done]
    assert store.list_events("missing") == []
    assert '"event_type": "run.started"' in store.export_jsonl("a")
    assert '"event_type": "run.completed"' in store.export_jsonl("a")


def test_stream_event_to_run_event_converts_text_delta():
    event = stream_event_to_run_event(TextDeltaEvent(content="hello"), run_id="run_1")

    assert event.event_type == RunEventType.MODEL_TEXT_DELTA
    assert event.run_id == "run_1"
    assert event.payload == {"content": "hello", "event_type": "text_delta", "legacy_event_type": "text_delta"}


def test_stream_event_to_run_event_converts_tool_call():
    event = stream_event_to_run_event(
        ToolCallEvent(tool_name="grep", args={"pattern": "AgentRunner"}, tool_call_id="tc_1"),
        run_id="run_1",
        step_id="step_2",
    )

    assert event.event_type == RunEventType.TOOL_CALL_STARTED
    assert event.step_id == "step_2"
    assert event.payload["tool_name"] == "grep"
    assert event.payload["args"] == {"pattern": "AgentRunner"}
    assert event.payload["tool_call_id"] == "tc_1"


def test_stream_event_to_run_event_sanitizes_done_event_payload():
    result = CodyResult(
        output="done",
        tool_traces=[ToolTrace(tool_name="read_file", args={"path": "README.md"}, result="ok")],
    )
    event = stream_event_to_run_event(DoneEvent(result=result), run_id="run_1")

    assert event.event_type == RunEventType.RUN_COMPLETED
    assert event.payload["legacy_event_type"] == "done"
    assert event.payload["result"]["output"] == "done"
    assert event.payload["result"]["tool_traces"][0]["tool_name"] == "read_file"


def test_agent_runner_records_stream_event_into_injected_trace_store():
    from cody.core.runner import AgentRunner

    store = InMemoryTraceStore()
    checkpoint_store = InMemoryCheckpointStore()
    runner = AgentRunner.__new__(AgentRunner)
    runner._trace_store = store
    runner._checkpoint_store = checkpoint_store

    runtime_event = runner._record_stream_event(
        TextDeltaEvent(content="streamed"),
        run_id="run_trace",
        step_id="step_000001",
    )

    assert runtime_event.event_type == RunEventType.MODEL_TEXT_DELTA
    assert runtime_event.run_id == "run_trace"
    assert runtime_event.step_id == "step_000001"
    assert store.list_events("run_trace") == [runtime_event]
    checkpoint = checkpoint_store.latest("run_trace")
    assert checkpoint is not None
    assert checkpoint.step_id == "step_000001"
    assert checkpoint.metadata["runtime_event_id"] == runtime_event.event_id
    assert runtime_event.payload["checkpoint_id"] == checkpoint.checkpoint_id


def test_agent_runner_exposes_runtime_store_properties():
    from cody.core.runner import AgentRunner

    store = InMemoryTraceStore()
    checkpoint_store = InMemoryCheckpointStore()
    runner = AgentRunner.__new__(AgentRunner)
    runner._trace_store = store
    runner._checkpoint_store = checkpoint_store

    assert runner.trace_store is store
    assert runner.checkpoint_store is checkpoint_store


def test_run_event_round_trips_from_dict():
    event = RunEvent(
        event_type=RunEventType.TOOL_CALL_STARTED,
        run_id="run_roundtrip",
        step_id="step_1",
        payload={"tool": "grep"},
    )

    restored = RunEvent.from_dict(event.to_dict())

    assert restored == event


def test_sqlite_trace_store_persists_events_across_instances(tmp_path):
    from cody.core.runtime import SQLiteTraceStore

    db_path = tmp_path / "trace.db"
    first = SQLiteTraceStore(db_path)
    first.append(RunEvent(RunEventType.RUN_STARTED, run_id="run_sqlite"))
    first.append(RunEvent(RunEventType.RUN_COMPLETED, run_id="run_sqlite"))
    first.append(RunEvent(RunEventType.RUN_STARTED, run_id="other"))

    second = SQLiteTraceStore(db_path)
    events = second.list_events("run_sqlite")

    assert [event.event_type for event in events] == [
        RunEventType.RUN_STARTED,
        RunEventType.RUN_COMPLETED,
    ]
    assert all(event.run_id == "run_sqlite" for event in events)
    assert '"event_type": "run.completed"' in second.export_jsonl("run_sqlite")


def test_runtime_run_and_step_records_transition_immutably():
    from cody.core.runtime import RunRecord, RunStatus, StepRecord, StepStatus, StepType

    run = RunRecord(task="refactor runtime", run_id="run_model")
    running = run.transition(RunStatus.RUNNING)
    completed = running.transition(RunStatus.COMPLETED, completed=True)

    assert run.status == RunStatus.CREATED
    assert running.status == RunStatus.RUNNING
    assert completed.status == RunStatus.COMPLETED
    assert completed.completed_at is not None
    assert completed.to_dict()["status"] == "completed"

    step = StepRecord(run_id=run.run_id, step_type=StepType.TOOL, step_id="step_model")
    started = step.start()
    done = started.complete(output_ref="artifact://tool-result")

    assert step.status == StepStatus.PENDING
    assert started.status == StepStatus.RUNNING
    assert done.status == StepStatus.COMPLETED
    assert done.output_ref == "artifact://tool-result"
    assert done.to_dict()["step_type"] == "tool"


def test_checkpoint_record_round_trips_from_dict():
    from cody.core.runtime import CheckpointRecord

    checkpoint = CheckpointRecord(
        checkpoint_id="ckpt_roundtrip",
        run_id="run_ckpt",
        step_id="step_1",
        workflow_state={"phase": "test"},
        message_state=[{"role": "user", "content": "go"}],
        artifact_refs=["artifact://plan"],
        file_refs=["diff://step_1"],
        child_run_ids=["run_child"],
        pending_approval_ids=["approval_1"],
        budget_state={"tokens": 10},
        metadata={"note": "snapshot"},
    )

    restored = CheckpointRecord.from_dict(checkpoint.to_dict())

    assert restored == checkpoint


def test_in_memory_checkpoint_store_tracks_latest_and_get():
    from cody.core.runtime import CheckpointRecord, InMemoryCheckpointStore

    store = InMemoryCheckpointStore()
    first = store.save(CheckpointRecord(checkpoint_id="ckpt_1", run_id="run_a", step_id="step_1"))
    second = store.save(
        CheckpointRecord(
            checkpoint_id="ckpt_2",
            parent_checkpoint_id=first.checkpoint_id,
            run_id="run_a",
            step_id="step_2",
        )
    )
    other = store.save(CheckpointRecord(checkpoint_id="ckpt_other", run_id="run_b", step_id="step_1"))

    assert store.list_checkpoints("run_a") == [first, second]
    assert store.latest("run_a") == second
    assert store.get("ckpt_1") == first
    assert store.list_checkpoints("run_b") == [other]
    assert store.latest("missing") is None


def test_sqlite_checkpoint_store_persists_across_instances(tmp_path):
    from cody.core.runtime import CheckpointRecord, SQLiteCheckpointStore

    db_path = tmp_path / "checkpoints.db"
    first_store = SQLiteCheckpointStore(db_path)
    first = first_store.save(
        CheckpointRecord(
            checkpoint_id="ckpt_sqlite_1",
            run_id="run_sqlite_ckpt",
            step_id="step_1",
            workflow_state={"node": "plan"},
        )
    )
    second = first_store.save(
        CheckpointRecord(
            checkpoint_id="ckpt_sqlite_2",
            parent_checkpoint_id=first.checkpoint_id,
            run_id="run_sqlite_ckpt",
            step_id="step_2",
            workflow_state={"node": "code"},
        )
    )

    second_store = SQLiteCheckpointStore(db_path)

    assert second_store.list_checkpoints("run_sqlite_ckpt") == [first, second]
    assert second_store.latest("run_sqlite_ckpt") == second
    assert second_store.get("ckpt_sqlite_1") == first
    assert second_store.latest("missing") is None


def test_agent_runner_checkpoint_captures_message_budget_and_refs():
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    from cody.core.runner import AgentRunner, _CircuitBreakerState

    store = InMemoryTraceStore()
    checkpoint_store = InMemoryCheckpointStore()
    runner = AgentRunner.__new__(AgentRunner)
    runner._trace_store = store
    runner._checkpoint_store = checkpoint_store
    runner._cb = _CircuitBreakerState(total_tokens=42, estimated_cost=0.25, step_count=3)

    message_state = runner._checkpoint_message_state([
        ModelRequest(parts=[UserPromptPart(content="please edit README")])
    ])
    artifact_refs, file_refs, child_run_ids, pending_approval_ids = runner._checkpoint_refs_for_event(
        ToolCallEvent(tool_name="read_file", args={"path": "README.md"}, tool_call_id="tc_read")
    )

    runtime_event = runner._record_stream_event(
        ToolCallEvent(tool_name="read_file", args={"path": "README.md"}, tool_call_id="tc_read"),
        run_id="run_rich_ckpt",
        step_id="step_rich",
        message_state=message_state,
        artifact_refs=artifact_refs,
        file_refs=file_refs,
        child_run_ids=child_run_ids,
        pending_approval_ids=pending_approval_ids,
    )

    checkpoint = checkpoint_store.latest("run_rich_ckpt")

    assert checkpoint is not None
    assert checkpoint.workflow_state["last_event_type"] == runtime_event.event_type.value
    assert checkpoint.workflow_state["last_event_payload"]["tool_name"] == "read_file"
    assert checkpoint.message_state[0]["message_type"] == "ModelRequest"
    assert checkpoint.artifact_refs == ["tool-call://tc_read"]
    assert checkpoint.file_refs == ["README.md"]
    assert checkpoint.child_run_ids == []
    assert checkpoint.pending_approval_ids == []
    assert checkpoint.budget_state == {
        "total_tokens": 42,
        "estimated_cost": 0.25,
        "step_count": 3,
    }
