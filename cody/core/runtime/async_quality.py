"""Async quality gates, standard evaluators, and workflow integration."""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
import sys
from typing import Any, Awaitable, Callable, Sequence

from ..sandbox import (
    FilesystemPolicy,
    LocalPolicySandboxBackend,
    SandboxExecutionRequest,
    SandboxHandle,
    SandboxSpec,
)
from .artifact import ArtifactRecord, ArtifactType, InMemoryArtifactStore, SQLiteArtifactStore
from .checkpoint import CheckpointRecord, InMemoryCheckpointStore, SQLiteCheckpointStore
from .events import RunEvent, RunEventType
from .quality import (
    EvaluationMetric,
    EvaluationResult,
    QualityGate,
    QualityGateDecision,
    QualityGateStatus,
)
from .trace import InMemoryTraceStore, SQLiteTraceStore
from .workflow import WorkflowNode, WorkflowState

AsyncEvaluator = Callable[
    [WorkflowState, EvaluationMetric],
    Awaitable[float | bool | dict[str, Any]] | float | bool | dict[str, Any],
]


class QualityGateFailure(RuntimeError):
    """A failed gate carrying state updates for an optional repair edge."""

    def __init__(
        self,
        decision: QualityGateDecision,
        *,
        state_updates: dict[str, Any],
        allow_fallback: bool,
    ):
        super().__init__(f"Quality gate failed: {decision.gate_id}")
        self.decision = decision
        self.state_updates = state_updates
        self.allow_fallback = allow_fallback


class AsyncQualityGateRunner:
    """Evaluate sync/async metrics and persist structured gate decisions."""

    def __init__(
        self,
        *,
        evaluators: dict[str, AsyncEvaluator] | None = None,
        trace_store: InMemoryTraceStore | SQLiteTraceStore | None = None,
        checkpoint_store: InMemoryCheckpointStore | SQLiteCheckpointStore | None = None,
        artifact_store: InMemoryArtifactStore | SQLiteArtifactStore | None = None,
    ):
        self.evaluators = evaluators or {}
        self.trace_store = trace_store or InMemoryTraceStore()
        self.checkpoint_store = checkpoint_store or InMemoryCheckpointStore()
        self.artifact_store = artifact_store

    async def evaluate(
        self,
        gate: QualityGate,
        state: WorkflowState,
    ) -> QualityGateDecision:
        results = tuple(
            await asyncio.gather(
                *(self._evaluate_metric(metric, state) for metric in gate.metrics)
            )
        )
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
        if (blocking and gate.block_on_required_failure) or weighted_score < gate.min_score:
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
        artifact_id = self._save_artifact(gate, decision, state)
        if artifact_id is not None:
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

    async def _evaluate_metric(
        self,
        metric: EvaluationMetric,
        state: WorkflowState,
    ) -> EvaluationResult:
        evaluator_id = metric.evaluator or metric.metric_id
        evaluator = self.evaluators.get(evaluator_id)
        if evaluator is None:
            return EvaluationResult(
                metric_id=metric.metric_id,
                score=0.0,
                passed=False,
                details={"error": f"No evaluator registered: {evaluator_id}"},
            )
        try:
            raw = evaluator(state, metric)
            if inspect.isawaitable(raw):
                raw = await raw
            if isinstance(raw, dict):
                score = float(raw.get("score", 0.0))
                details = dict(raw)
            elif isinstance(raw, bool):
                score = 1.0 if raw else 0.0
                details = {"raw": raw}
            else:
                score = float(raw)
                details = {"raw": raw}
        except Exception as exc:
            score = 0.0
            details = {"error": str(exc), "error_type": type(exc).__name__}
        score = min(1.0, max(0.0, score))
        return EvaluationResult(
            metric_id=metric.metric_id,
            score=score,
            passed=score >= metric.threshold,
            details=details,
        )

    def _save_artifact(
        self,
        gate: QualityGate,
        decision: QualityGateDecision,
        state: WorkflowState,
    ) -> str | None:
        if self.artifact_store is None or not gate.artifact_outputs:
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

    def _record(
        self,
        gate: QualityGate,
        decision: QualityGateDecision,
        state: WorkflowState,
    ) -> None:
        event_type = (
            RunEventType.QUALITY_GATE_FAILED
            if decision.status == QualityGateStatus.FAILED
            else RunEventType.QUALITY_GATE_PASSED
        )
        event = RunEvent(
            event_type,
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
                metadata={
                    "runtime_event_id": event.event_id,
                    "runtime_event_type": event.event_type.value,
                },
            )
        )
        event.payload.setdefault("checkpoint_id", checkpoint.checkpoint_id)
        self.trace_store.append(event)


def async_quality_gate_node_handler(runner: AsyncQualityGateRunner):
    """Build a workflow node handler with bounded repair-loop semantics."""

    async def handler(state: WorkflowState, node: WorkflowNode) -> dict[str, Any]:
        gate = _quality_gate_from_node(node)
        attempts = dict(state.data.get("quality_gate_attempts") or {})
        attempt = int(attempts.get(gate.gate_id, 0)) + 1
        attempts[gate.gate_id] = attempt
        decision = await runner.evaluate(gate, state)
        decisions = dict(state.data.get("quality_gates") or {})
        decisions[gate.gate_id] = decision.to_dict()
        updates = {
            "quality_gate_attempts": attempts,
            "quality_gates": decisions,
            "quality_gate_passed": decision.status != QualityGateStatus.FAILED,
            "quality_gate_failed": decision.status == QualityGateStatus.FAILED,
        }
        if decision.status == QualityGateStatus.FAILED:
            max_repairs = max(0, int(node.metadata.get("max_repairs", 0)))
            raise QualityGateFailure(
                decision,
                state_updates=updates,
                allow_fallback=attempt <= max_repairs,
            )
        return updates

    return handler


def command_evaluator(
    command: Sequence[str],
    *,
    workdir: str | Path,
    timeout: float = 300.0,
    max_output_chars: int = 20_000,
    sandbox: SandboxHandle | None = None,
) -> AsyncEvaluator:
    """Create a no-shell evaluator for tests, lint, type, security, or coverage."""

    argv = tuple(str(part) for part in command)
    cwd = Path(workdir).resolve()
    binding: dict[str, SandboxHandle | None] = {"sandbox": sandbox}

    async def evaluate(_state: WorkflowState, _metric: EvaluationMetric) -> dict[str, Any]:
        handle = binding["sandbox"]
        owned = False
        if handle is None:
            # Standalone evaluator calls still cross the common backend API.
            # Runtime use binds the Run's hardened handle below.
            handle = await LocalPolicySandboxBackend().create(
                SandboxSpec(
                    run_id=_state.run_id,
                    workdir=cwd,
                    backend="local-policy",
                    filesystem=FilesystemPolicy(
                        read_roots=(cwd,), write_roots=(cwd,)
                    ),
                )
            )
            owned = True
        try:
            result = await handle.exec(
                SandboxExecutionRequest(
                    argv=argv,
                    cwd=cwd,
                    timeout_seconds=timeout,
                    capture_limit=max_output_chars,
                )
            )
        except FileNotFoundError as exc:
            return {"score": 0.0, "error": str(exc), "command": list(argv)}
        finally:
            if owned:
                await handle.terminate()
        if result.timed_out:
            return {
                "score": 0.0,
                "error": f"Command timed out after {timeout}s",
                "command": list(argv),
            }
        return {
            "score": 1.0 if result.returncode == 0 else 0.0,
            "returncode": result.returncode,
            "command": list(argv),
            "stdout": result.stdout[-max_output_chars:],
            "stderr": result.stderr[-max_output_chars:],
        }

    def bind(handle: SandboxHandle) -> None:
        binding["sandbox"] = handle

    setattr(evaluate, "bind_sandbox", bind)
    return evaluate


def diff_risk_evaluator(
    state: WorkflowState,
    _metric: EvaluationMetric,
) -> dict[str, Any]:
    """Score structured diff statistics; 1.0 means lowest estimated risk."""

    stats = dict(state.data.get("diff_stats") or {})
    files = max(0, int(stats.get("files_changed", 0)))
    lines = max(0, int(stats.get("lines_added", 0))) + max(
        0, int(stats.get("lines_deleted", 0))
    )
    sensitive = max(0, int(stats.get("sensitive_files", 0)))
    risk = min(
        1.0,
        min(files / 20, 1.0) * 0.25
        + min(lines / 1000, 1.0) * 0.35
        + min(sensitive / 3, 1.0) * 0.4,
    )
    return {
        "score": 1.0 - risk,
        "risk": risk,
        "files_changed": files,
        "lines_changed": lines,
        "sensitive_files": sensitive,
    }


def standard_quality_evaluators(
    workdir: str | Path,
    *,
    commands: dict[str, Sequence[str]] | None = None,
) -> dict[str, AsyncEvaluator]:
    """Return standard tests/lint/type/security/coverage/diff-risk evaluators."""

    defaults: dict[str, Sequence[str]] = {
        "tests": (sys.executable, "-m", "pytest", "-q"),
        "lint": ("ruff", "check", "."),
        "typecheck": ("mypy", "cody"),
        "security": (sys.executable, "-m", "pip_audit"),
        "coverage": (sys.executable, "-m", "coverage", "report"),
    }
    defaults.update(commands or {})
    evaluators = {
        name: command_evaluator(command, workdir=workdir)
        for name, command in defaults.items()
    }
    evaluators["diff_risk"] = diff_risk_evaluator
    return evaluators


def _quality_gate_from_node(node: WorkflowNode) -> QualityGate:
    raw = dict(node.metadata.get("quality_gate") or {})
    metrics = tuple(
        EvaluationMetric(
            metric_id=str(metric["metric_id"]),
            name=metric.get("name"),
            threshold=float(metric.get("threshold", 1.0)),
            weight=float(metric.get("weight", 1.0)),
            required=bool(metric.get("required", True)),
            evaluator=metric.get("evaluator"),
            metadata=dict(metric.get("metadata") or {}),
        )
        for metric in raw.get("metrics") or []
    )
    if not metrics:
        raise ValueError(f"Quality gate node has no metrics: {node.node_id}")
    return QualityGate(
        gate_id=str(raw.get("gate_id") or node.node_id),
        metrics=metrics,
        min_score=float(raw.get("min_score", 1.0)),
        block_on_required_failure=bool(raw.get("block_on_required_failure", True)),
        artifact_outputs=bool(raw.get("artifact_outputs", True)),
        metadata=dict(raw.get("metadata") or {}),
    )
