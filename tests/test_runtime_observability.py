from cody.core.runtime import (
    ArtifactRecord,
    ArtifactType,
    RunEvent,
    RunEventType,
    RuntimeStoreBundle,
)


def test_observability_snapshot_joins_canonical_runtime_records():
    stores = RuntimeStoreBundle.in_memory()
    run_id = "run_metrics"
    stores.trace_store.extend([
        RunEvent(RunEventType.RUN_STARTED, run_id=run_id),
        RunEvent(RunEventType.WORKFLOW_NODE_STARTED, run_id=run_id),
        RunEvent(RunEventType.TOOL_CALL_STARTED, run_id=run_id),
        RunEvent(RunEventType.MODEL_RETRYING, run_id=run_id),
        RunEvent(RunEventType.MODEL_COMPLETED, run_id=run_id),
        RunEvent(
            RunEventType.RUN_COMPLETED,
            run_id=run_id,
            payload={"usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14}},
        ),
    ])
    stores.artifact_store.save(ArtifactRecord(
        run_id=run_id, artifact_type=ArtifactType.GENERIC, content="result"
    ))

    response = stores.interface().get_metrics(run_id)

    metrics = response.data["metrics"]
    assert metrics["event_count"] == 6
    assert metrics["step_count"] == 1
    assert metrics["tool_calls"] == 1
    assert metrics["model_retries"] == 1
    assert metrics["usage"]["total_tokens"] == 14
    assert metrics["artifacts"] == 1
