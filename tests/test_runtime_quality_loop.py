import asyncio
import sys

import pytest

from cody.core.runtime import (
    ArtifactType,
    AsyncQualityGateRunner,
    CodyRuntime,
    EvaluationMetric,
    QualityGate,
    QualityGateFailure,
    QualityGateStatus,
    RunEventType,
    RunStatus,
    Workflow,
    WorkflowEdgeType,
    WorkflowNodeType,
    WorkflowState,
    command_evaluator,
    diff_risk_evaluator,
)


class UnusedRunner:
    pass


def repair_workflow(*, max_repairs: int):
    return (
        Workflow("quality-repair", workflow_id=f"workflow_quality_{max_repairs}")
        .node(
            "gate",
            WorkflowNodeType.QUALITY_GATE,
            metadata={
                "max_repairs": max_repairs,
                "quality_gate": {
                    "gate_id": "tests_gate",
                    "metrics": [
                        {
                            "metric_id": "tests",
                            "threshold": 1.0,
                            "required": True,
                        }
                    ],
                },
            },
        )
        .node("repair", WorkflowNodeType.FUNCTION)
        .node("done", WorkflowNodeType.FUNCTION)
        .edge("gate", "done")
        .edge(
            "gate",
            "repair",
            edge_type=WorkflowEdgeType.FALLBACK,
            metadata={"allow_revisit": True},
        )
        .edge(
            "repair",
            "gate",
            metadata={"allow_revisit": True},
        )
        .compile()
    )


@pytest.mark.asyncio
async def test_quality_gate_failure_repairs_and_rechecks_before_advancing():
    evaluations = []

    async def tests_evaluator(state, _metric):
        evaluations.append(bool(state.data.get("fixed")))
        return bool(state.data.get("fixed"))

    async def function_handler(_state, node):
        if node.node_id == "repair":
            return {"fixed": True}
        return {"delivered": True}

    runtime = CodyRuntime(
        UnusedRunner(),
        quality_evaluators={"tests": tests_evaluator},
        node_handlers={"function": function_handler},
        poll_interval=0,
    )
    run = await runtime.start(
        repair_workflow(max_repairs=2),
        run_id="run_quality_repair",
    )
    result = await run.result()

    assert evaluations == [False, True]
    assert result.run.status == RunStatus.COMPLETED
    assert result.state.data["fixed"] is True
    assert result.state.data["delivered"] is True
    assert result.state.data["quality_gate_passed"] is True
    assert result.state.data["quality_gate_attempts"] == {"tests_gate": 2}
    reports = runtime.stores.artifact_store.list(
        run_id=run.run_id,
        artifact_type=ArtifactType.REVIEW,
    )
    assert len(reports) == 2
    quality_events = [
        event.event_type
        for event in runtime.stores.trace_store.list_events(run.run_id)
        if event.event_type
        in {RunEventType.QUALITY_GATE_FAILED, RunEventType.QUALITY_GATE_PASSED}
    ]
    assert quality_events == [
        RunEventType.QUALITY_GATE_FAILED,
        RunEventType.QUALITY_GATE_PASSED,
    ]


@pytest.mark.asyncio
async def test_quality_gate_exhausts_bounded_repairs_and_fails_run():
    repairs = 0

    async def repair(_state, _node):
        nonlocal repairs
        repairs += 1
        return {"fixed": False}

    runtime = CodyRuntime(
        UnusedRunner(),
        quality_evaluators={"tests": lambda _state, _metric: False},
        node_handlers={"function": repair},
    )
    run = await runtime.start(
        repair_workflow(max_repairs=1),
        run_id="run_quality_exhausted",
    )

    with pytest.raises(QualityGateFailure):
        await run.result()

    assert repairs == 1
    assert run.record.status == RunStatus.FAILED
    decisions = runtime.stores.artifact_store.list(
        run_id=run.run_id,
        artifact_type=ArtifactType.REVIEW,
    )
    assert len(decisions) == 2


@pytest.mark.asyncio
async def test_async_quality_runner_evaluates_independent_metrics_concurrently():
    started = set()
    gate = asyncio.Event()

    async def evaluator(_state, metric):
        started.add(metric.metric_id)
        if len(started) == 2:
            gate.set()
        await asyncio.wait_for(gate.wait(), timeout=0.2)
        return True

    runner = AsyncQualityGateRunner(
        evaluators={"one": evaluator, "two": evaluator}
    )
    decision = await runner.evaluate(
        QualityGate.create(
            [EvaluationMetric("one"), EvaluationMetric("two")],
            gate_id="parallel_metrics",
        ),
        WorkflowState(workflow_id="quality", run_id="run_quality_parallel"),
    )

    assert started == {"one", "two"}
    assert decision.status == QualityGateStatus.PASSED


@pytest.mark.asyncio
async def test_command_evaluator_records_exit_status_without_shell(tmp_path):
    evaluator = command_evaluator(
        (sys.executable, "-c", "print('QUALITY_OK')"),
        workdir=tmp_path,
    )
    result = await evaluator(
        WorkflowState(workflow_id="quality", run_id="run_command_gate"),
        EvaluationMetric("command"),
    )

    assert result["score"] == 1.0
    assert result["returncode"] == 0
    assert "QUALITY_OK" in result["stdout"]


def test_diff_risk_evaluator_scores_structured_change_risk():
    low = diff_risk_evaluator(
        WorkflowState(
            workflow_id="quality",
            run_id="run_low_risk",
            data={
                "diff_stats": {
                    "files_changed": 1,
                    "lines_added": 5,
                    "lines_deleted": 3,
                    "sensitive_files": 0,
                }
            },
        ),
        EvaluationMetric("diff_risk"),
    )
    high = diff_risk_evaluator(
        WorkflowState(
            workflow_id="quality",
            run_id="run_high_risk",
            data={
                "diff_stats": {
                    "files_changed": 30,
                    "lines_added": 1000,
                    "lines_deleted": 500,
                    "sensitive_files": 3,
                }
            },
        ),
        EvaluationMetric("diff_risk"),
    )

    assert low["score"] > high["score"]
    assert high["score"] == 0.0
