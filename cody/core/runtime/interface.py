"""User-facing runtime service for CLI, TUI, and Web API adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .approval import ApprovalStatus, InMemoryApprovalStore, SQLiteApprovalStore
from .audit import InMemoryRuntimeAuditStore, RuntimeAuditRecord, SQLiteRuntimeAuditStore
from .artifact import ArtifactRecord, ArtifactType, InMemoryArtifactStore, SQLiteArtifactStore
from .checkpoint import InMemoryCheckpointStore, SQLiteCheckpointStore
from .control import SQLiteWorkflowControlState, WorkflowControlState
from .models import RunStatus
from .observability import RuntimeObservability
from .registry import InMemoryRunStore, SQLiteRunStore
from .redaction import redact_secrets
from .security import RuntimeActionPolicy
from .timeline import TimelineAPI
from .trace import InMemoryTraceStore, SQLiteTraceStore


@dataclass(frozen=True)
class RuntimeAPIResponse:
    """Stable response envelope for command, TUI, and HTTP adapters."""

    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "data": self.data, "error": self.error}


class RuntimeInterface:
    """Thin application-service layer over runtime stores.

    This class intentionally contains no terminal or HTTP framework dependency.
    A CLI command, TUI screen, or Web endpoint can call the same methods and get
    the same `RuntimeAPIResponse` shape.
    """

    def __init__(
        self,
        *,
        trace_store: InMemoryTraceStore | SQLiteTraceStore,
        checkpoint_store: InMemoryCheckpointStore | SQLiteCheckpointStore | None = None,
        artifact_store: InMemoryArtifactStore | SQLiteArtifactStore | None = None,
        approval_store: InMemoryApprovalStore | SQLiteApprovalStore | None = None,
        run_store: InMemoryRunStore | SQLiteRunStore | None = None,
        action_policy: RuntimeActionPolicy | None = None,
        audit_store: InMemoryRuntimeAuditStore | SQLiteRuntimeAuditStore | None = None,
        control_store: WorkflowControlState | SQLiteWorkflowControlState | None = None,
    ):
        self.trace_store = trace_store
        self.checkpoint_store = checkpoint_store
        self.artifact_store = artifact_store
        self.approval_store = approval_store
        self.run_store = run_store
        self.action_policy = action_policy
        self.audit_store = audit_store
        self.control_store = control_store
        self.timeline_api = TimelineAPI(
            trace_store=trace_store,
            checkpoint_store=checkpoint_store,
            artifact_store=artifact_store,
        )
        self.observability = RuntimeObservability(
            trace_store, checkpoint_store, artifact_store
        )

    def list_runs(
        self,
        *,
        status: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> RuntimeAPIResponse:
        if self.run_store is None:
            run_ids = sorted({event.run_id for event in self.trace_store.list_events() if event.run_id})
            runs = [{"run_id": run_id} for run_id in run_ids]
            return RuntimeAPIResponse(
                ok=True,
                data=_page("runs", runs, offset=offset, limit=limit),
            )
        run_status = RunStatus(status) if status else None
        runs = [run.to_dict() for run in self.run_store.list_runs(status=run_status)]
        runs.sort(key=lambda run: run["updated_at"], reverse=True)
        return RuntimeAPIResponse(
            ok=True,
            data=_page("runs", runs, offset=offset, limit=limit),
        )

    def get_run(self, run_id: str) -> RuntimeAPIResponse:
        if self.run_store is None:
            events = self.trace_store.list_events(run_id)
            if not events:
                return RuntimeAPIResponse(ok=False, error=f"Run not found: {run_id}")
            return RuntimeAPIResponse(ok=True, data={"run": {"run_id": run_id}})
        run = self.run_store.get_run(run_id)
        if run is None:
            return RuntimeAPIResponse(ok=False, error=f"Run not found: {run_id}")
        return RuntimeAPIResponse(ok=True, data={"run": run.to_dict()})

    def list_steps(self, run_id: str) -> RuntimeAPIResponse:
        if self.run_store is None:
            return RuntimeAPIResponse(ok=False, error="Run store is not configured")
        steps = [step.to_dict() for step in self.run_store.list_steps(run_id)]
        return RuntimeAPIResponse(ok=True, data={"steps": steps})

    def request_pause(
        self,
        run_id: str,
        *,
        before_node_id: str | None = None,
    ) -> RuntimeAPIResponse:
        if self.control_store is None:
            return RuntimeAPIResponse(ok=False, error="Control store is not configured")
        self.control_store.request_pause(run_id, before_node_id=before_node_id)
        return RuntimeAPIResponse(
            ok=True,
            data={"run_id": run_id, "control": "pause_requested"},
        )

    def request_cancel(
        self,
        run_id: str,
        *,
        before_node_id: str | None = None,
    ) -> RuntimeAPIResponse:
        if self.control_store is None:
            return RuntimeAPIResponse(ok=False, error="Control store is not configured")
        self.control_store.request_cancel(run_id, before_node_id=before_node_id)
        return RuntimeAPIResponse(
            ok=True,
            data={"run_id": run_id, "control": "cancel_requested"},
        )

    def clear_control(self, run_id: str) -> RuntimeAPIResponse:
        if self.control_store is None:
            return RuntimeAPIResponse(ok=False, error="Control store is not configured")
        self.control_store.clear_pause(run_id)
        self.control_store.clear_cancel(run_id)
        return RuntimeAPIResponse(
            ok=True,
            data={"run_id": run_id, "control": "cleared"},
        )

    def get_timeline(self, run_id: str) -> RuntimeAPIResponse:
        return RuntimeAPIResponse(ok=True, data=self.timeline_api.export(run_id))

    def get_metrics(self, run_id: str) -> RuntimeAPIResponse:
        return RuntimeAPIResponse(
            ok=True, data={"metrics": self.observability.snapshot(run_id)}
        )

    def get_frame(self, run_id: str, index: int) -> RuntimeAPIResponse:
        return RuntimeAPIResponse(ok=True, data=self.timeline_api.frame(run_id, index).to_dict())

    def replay(self, run_id: str, *, until_index: int | None = None) -> RuntimeAPIResponse:
        return RuntimeAPIResponse(ok=True, data={"events": self.timeline_api.replay(run_id, until_index=until_index)})

    def list_checkpoints(self, run_id: str) -> RuntimeAPIResponse:
        if self.checkpoint_store is None:
            return RuntimeAPIResponse(ok=False, error="Checkpoint store is not configured")
        checkpoints = [
            checkpoint.to_dict()
            for checkpoint in self.checkpoint_store.list_checkpoints(run_id)
        ]
        return RuntimeAPIResponse(ok=True, data={"checkpoints": checkpoints})

    def get_checkpoint(self, checkpoint_id: str) -> RuntimeAPIResponse:
        if self.checkpoint_store is None:
            return RuntimeAPIResponse(ok=False, error="Checkpoint store is not configured")
        checkpoint = self.checkpoint_store.get(checkpoint_id)
        if checkpoint is None:
            return RuntimeAPIResponse(
                ok=False,
                error=f"Checkpoint not found: {checkpoint_id}",
            )
        return RuntimeAPIResponse(ok=True, data={"checkpoint": checkpoint.to_dict()})

    def list_approvals(self, *, run_id: str | None = None, status: str | None = None) -> RuntimeAPIResponse:
        if self.approval_store is None:
            return RuntimeAPIResponse(ok=False, error="Approval store is not configured")
        approval_status = ApprovalStatus(status) if status else None
        approvals = [approval.to_dict() for approval in self.approval_store.list(run_id=run_id, status=approval_status)]
        return RuntimeAPIResponse(ok=True, data={"approvals": approvals})

    def approve(self, approval_id: str, response: dict[str, Any] | None = None) -> RuntimeAPIResponse:
        if self.approval_store is None:
            return RuntimeAPIResponse(ok=False, error="Approval store is not configured")
        approval = self.approval_store.approve(approval_id, response=response)
        return RuntimeAPIResponse(ok=True, data={"approval": approval.to_dict()})

    def reject(self, approval_id: str, response: dict[str, Any] | None = None) -> RuntimeAPIResponse:
        if self.approval_store is None:
            return RuntimeAPIResponse(ok=False, error="Approval store is not configured")
        approval = self.approval_store.reject(approval_id, response=response)
        return RuntimeAPIResponse(ok=True, data={"approval": approval.to_dict()})

    def list_artifacts(self, *, run_id: str | None = None, step_id: str | None = None) -> RuntimeAPIResponse:
        if self.artifact_store is None:
            return RuntimeAPIResponse(ok=False, error="Artifact store is not configured")
        artifacts = [artifact.to_dict() for artifact in self.artifact_store.list(run_id=run_id, step_id=step_id)]
        return RuntimeAPIResponse(ok=True, data={"artifacts": artifacts})

    def get_artifact(self, artifact_id: str) -> RuntimeAPIResponse:
        if self.artifact_store is None:
            return RuntimeAPIResponse(ok=False, error="Artifact store is not configured")
        artifact = self.artifact_store.get(artifact_id)
        if artifact is None:
            return RuntimeAPIResponse(ok=False, error=f"Artifact not found: {artifact_id}")
        return RuntimeAPIResponse(ok=True, data={"artifact": artifact.to_dict()})

    def list_audit(
        self,
        *,
        actor_id: str | None = None,
        action: str | None = None,
    ) -> RuntimeAPIResponse:
        if self.audit_store is None:
            return RuntimeAPIResponse(ok=False, error="Audit store is not configured")
        records = [
            record.to_dict()
            for record in self.audit_store.list(actor_id=actor_id, action=action)
        ]
        return RuntimeAPIResponse(ok=True, data={"audit_records": records})

    def save_artifact(
        self,
        *,
        run_id: str,
        content: dict[str, Any] | str,
        artifact_type: str = ArtifactType.GENERIC.value,
        step_id: str | None = None,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeAPIResponse:
        if self.artifact_store is None:
            return RuntimeAPIResponse(ok=False, error="Artifact store is not configured")
        artifact = self.artifact_store.save(
            ArtifactRecord(
                run_id=run_id,
                step_id=step_id,
                artifact_type=ArtifactType(artifact_type),
                name=name,
                content=content,
                metadata=metadata or {},
            )
        )
        return RuntimeAPIResponse(ok=True, data={"artifact": artifact.to_dict()})

    def handle(self, action: str, *, actor_id: str | None = None, **kwargs: Any) -> RuntimeAPIResponse:
        """Dispatch a CLI/TUI/Web action name to a service method."""

        if self.action_policy is not None:
            decision = self.action_policy.authorize(action, actor_id=actor_id)
            if not decision.allowed:
                response = RuntimeAPIResponse(ok=False, error=decision.reason)
                self._audit(action, actor_id=actor_id, response=response, kwargs=kwargs)
                return response

        actions = {
            "runs.list": self.list_runs,
            "runs.get": self.get_run,
            "runs.steps": self.list_steps,
            "runs.pause": self.request_pause,
            "runs.cancel": self.request_cancel,
            "runs.clear_control": self.clear_control,
            "timeline.get": self.get_timeline,
            "metrics.get": self.get_metrics,
            "timeline.frame": self.get_frame,
            "timeline.replay": self.replay,
            "checkpoints.list": self.list_checkpoints,
            "checkpoints.get": self.get_checkpoint,
            "approvals.list": self.list_approvals,
            "approvals.approve": self.approve,
            "approvals.reject": self.reject,
            "artifacts.list": self.list_artifacts,
            "artifacts.get": self.get_artifact,
            "artifacts.save": self.save_artifact,
            "audit.list": self.list_audit,
        }
        handler = actions.get(action)
        if handler is None:
            response = RuntimeAPIResponse(ok=False, error=f"Unknown runtime action: {action}")
            self._audit(action, actor_id=actor_id, response=response, kwargs=kwargs)
            return response
        response = handler(**kwargs)
        self._audit(action, actor_id=actor_id, response=response, kwargs=kwargs)
        return response

    def _audit(self, action: str, *, actor_id: str | None, response: RuntimeAPIResponse, kwargs: dict[str, Any]) -> None:
        if self.audit_store is None:
            return
        effect = self.action_policy.effect_for(action).value if self.action_policy else _effect_for(action)
        self.audit_store.append(
            RuntimeAuditRecord(
                action=action,
                actor_id=actor_id,
                ok=response.ok,
                effect=effect,
                run_id=kwargs.get("run_id"),
                error=response.error,
                metadata={"params": _safe_audit_params(kwargs)},
            )
        )


def _effect_for(action: str) -> str:
    return (
        "write"
        if action
        in {
            "runs.pause",
            "runs.cancel",
            "runs.clear_control",
            "approvals.approve",
            "approvals.reject",
            "artifacts.save",
        }
        else "read"
    )


def _safe_audit_params(params: dict[str, Any]) -> dict[str, Any]:
    redacted = redact_secrets(params)
    if "content" in redacted:
        redacted["content"] = "<redacted>"
    return redacted


def _page(
    key: str,
    items: list[dict[str, Any]],
    *,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    safe_offset = max(0, offset)
    safe_limit = min(1000, max(1, limit))
    return {
        key: items[safe_offset : safe_offset + safe_limit],
        "total": len(items),
        "offset": safe_offset,
        "limit": safe_limit,
    }
