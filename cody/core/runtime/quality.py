"""Evaluation and quality-gate primitives for runtime outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from uuid import uuid4

from .artifact import ArtifactRecord, ArtifactType, InMemoryArtifactStore, SQLiteArtifactStore
from .checkpoint import CheckpointRecord, InMemoryCheckpointStore, SQLiteCheckpointStore
from .events import RunEvent, RunEventType
from .trace import InMemoryTraceStore, SQLiteTraceStore
from .workflow import WorkflowState

Evaluator = Callable[[WorkflowState, "EvaluationMetric"], float | bool | dict[str, Any]]


class QualityGateStatus(str, Enum):
    """Final decision status for a quality gate."""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"


@dataclass(frozen=True)
class EvaluationMetric:
    """One measurable quality criterion."""

    metric_id: str
    name: str | None = None
    threshold: float = 1.0
    weight: float = 1.0
    required: bool = True
    evaluator: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "name": self.name,
            "threshold": self.threshold,
            "weight": self.weight,
            "required": self.required,
            "evaluator": self.evaluator,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class EvaluationResult:
    """Measured result for one metric."""

    metric_id: str
    score: float
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "score": self.score,
            "passed": self.passed,
            "details": self.details,
        }


@dataclass(frozen=True)
class QualityGate:
    """Collection of metrics that determines whether workflow output can advance."""

    gate_id: str
    metrics: tuple[EvaluationMetric, ...]
    min_score: float = 1.0
    block_on_required_failure: bool = True
    artifact_outputs: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        metrics: list[EvaluationMetric] | tuple[EvaluationMetric, ...],
        *,
        gate_id: str | None = None,
        min_score: float = 1.0,
        block_on_required_failure: bool = True,
        artifact_outputs: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> "QualityGate":
        return cls(
            gate_id=gate_id or f"quality_gate_{uuid4().hex}",
            metrics=tuple(metrics),
            min_score=min_score,
            block_on_required_failure=block_on_required_failure,
            artifact_outputs=artifact_outputs,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "min_score": self.min_score,
            "block_on_required_failure": self.block_on_required_failure,
            "artifact_outputs": self.artifact_outputs,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class QualityGateDecision:
    """Outcome from evaluating a quality gate."""

    gate_id: str
    status: QualityGateStatus
    score: float
    results: tuple[EvaluationResult, ...]
    blocking_failures: tuple[str, ...] = ()
    artifact_id: str | None = None

    @property
    def passed(self) -> bool:
        return self.status == QualityGateStatus.PASSED

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "status": self.status.value,
            "score": self.score,
            "results": [result.to_dict() for result in self.results],
            "blocking_failures": list(self.blocking_failures),
            "artifact_id": self.artifact_id,
        }


class QualityGateRunner:
    """Evaluate workflow state and persist quality decisions."""

    def __init__(
        self,
        *,
        evaluators: dict[str, Evaluator] | None = None,
        trace_store: InMemoryTraceStore | SQLiteTraceStore | None = None,
        checkpoint_store: InMemoryCheckpointStore | SQLiteCheckpointStore | None = None,
        artifact_store: InMemoryArtifactStore | SQLiteArtifactStore | None = None,
    ):
        self.evaluators = evaluators or {}
        self.trace_store = trace_store or InMemoryTraceStore()
        self.checkpoint_store = checkpoint_store or InMemoryCheckpointStore()
        self.artifact_store = artifact_store

    def evaluate(self, gate: QualityGate, state: WorkflowState) -> QualityGateDecision:
        results = tuple(self._evaluate_metric(metric, state) for metric in gate.metrics)
        weighted_total = sum(metric.weight for metric in gate.metrics) or 1.0
        weighted_score = sum(
            result.score * metric.weight
            for result, metric in zip(results, gate.metrics, strict=True)
        ) / weighted_total
        blocking = tuple(
            result.metric_id
            for result, metric in zip(results, gate.metrics, strict=True)
            if metric.required and not result.passed
        )
        failed_required = bool(blocking) and gate.block_on_required_failure
        if failed_required or weighted_score < gate.min_score:
            status = QualityGateStatus.FAILED
        elif any(not result.passed for result in results):
            status = QualityGateStatus.WARNING
        else:
            status = QualityGateStatus.PASSED

        decision = QualityGateDecision(
            gate_id=gate.gate_id,
            status=status,
            score=weighted_score,
            results=results,
            blocking_failures=blocking,
        )
        artifact_id = self._save_artifact(gate, decision, state) if gate.artifact_outputs else None
        if artifact_id:
            decision = QualityGateDecision(
                gate_id=decision.gate_id,
                status=decision.status,
                score=decision.score,
                results=decision.results,
                blocking_failures=decision.blocking_failures,
                artifact_id=artifact_id,
            )
        self._record(gate, decision, state)
        return decision

    def assert_passed(self, gate: QualityGate, state: WorkflowState) -> QualityGateDecision:
        decision = self.evaluate(gate, state)
        if not decision.passed:
            raise RuntimeError(f"Quality gate failed: {decision.to_dict()}")
        return decision

    def _evaluate_metric(self, metric: EvaluationMetric, state: WorkflowState) -> EvaluationResult:
        evaluator_id = metric.evaluator or metric.metric_id
        evaluator = self.evaluators.get(evaluator_id)
        if evaluator is None:
            raise KeyError(f"No evaluator registered for metric: {evaluator_id}")
        raw = evaluator(state, metric)
        if isinstance(raw, dict):
            score = float(raw.get("score", 0.0))
            details = dict(raw)
        elif isinstance(raw, bool):
            score = 1.0 if raw else 0.0
            details = {"raw": raw}
        else:
            score = float(raw)
            details = {"raw": raw}
        return EvaluationResult(
            metric_id=metric.metric_id,
            score=score,
            passed=score >= metric.threshold,
            details=details,
        )

    def _save_artifact(self, gate: QualityGate, decision: QualityGateDecision, state: WorkflowState) -> str | None:
        if self.artifact_store is None:
            return None
        artifact = self.artifact_store.save(
            ArtifactRecord(
                run_id=state.run_id,
                step_id=f"quality_gate_{gate.gate_id}",
                artifact_type=ArtifactType.REVIEW,
                name=f"{gate.gate_id}.quality.json",
                content=decision.to_dict(),
                metadata={"gate": gate.to_dict()},
            )
        )
        return artifact.artifact_id

    def _record(self, gate: QualityGate, decision: QualityGateDecision, state: WorkflowState) -> RunEvent:
        event = RunEvent(
            event_type=RunEventType.WORKFLOW_NODE_COMPLETED,
            run_id=state.run_id,
            step_id=f"quality_gate_{gate.gate_id}",
            payload={"gate": gate.to_dict(), "decision": decision.to_dict()},
        )
        checkpoint = self.checkpoint_store.save(
            CheckpointRecord(
                run_id=state.run_id,
                step_id=event.step_id or f"quality_gate_{gate.gate_id}",
                workflow_state=state.to_dict(),
                artifact_refs=[decision.artifact_id] if decision.artifact_id else [],
                metadata={"runtime_event_id": event.event_id, "runtime_event_type": event.event_type.value},
            )
        )
        event.payload.setdefault("checkpoint_id", checkpoint.checkpoint_id)
        self.trace_store.append(event)
        return event
