"""First-class runtime records for runs and steps."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class RunStatus(str, Enum):
    """Lifecycle states for a runtime run."""

    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class StepStatus(str, Enum):
    """Lifecycle states for a runtime step."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class StepType(str, Enum):
    """High-level categories for runtime steps."""

    MODEL = "model"
    TOOL = "tool"
    HANDOFF = "handoff"
    APPROVAL = "approval"
    CHECKPOINT = "checkpoint"
    CONTEXT = "context"
    SESSION = "session"
    SYSTEM = "system"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class RunRecord:
    """Durable metadata for a single agent/workflow run."""

    task: str
    run_id: str = field(default_factory=lambda: f"run_{uuid4().hex}")
    status: RunStatus = RunStatus.CREATED
    parent_run_id: str | None = None
    workflow_id: str | None = None
    session_id: str | None = None
    project_id: str | None = None
    workdir: str | None = None
    branch: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    completed_at: datetime | None = None

    def transition(self, status: RunStatus, *, completed: bool = False) -> "RunRecord":
        """Return a copy with updated lifecycle status."""

        now = utc_now()
        return RunRecord(
            task=self.task,
            run_id=self.run_id,
            status=status,
            parent_run_id=self.parent_run_id,
            workflow_id=self.workflow_id,
            session_id=self.session_id,
            project_id=self.project_id,
            workdir=self.workdir,
            branch=self.branch,
            metadata=dict(self.metadata),
            created_at=self.created_at,
            updated_at=now,
            completed_at=now if completed else self.completed_at,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunRecord":
        return cls(
            run_id=data["run_id"],
            parent_run_id=data.get("parent_run_id"),
            workflow_id=data.get("workflow_id"),
            session_id=data.get("session_id"),
            project_id=data.get("project_id"),
            task=data["task"],
            status=RunStatus(data.get("status", RunStatus.CREATED.value)),
            workdir=data.get("workdir"),
            branch=data.get("branch"),
            metadata=dict(data.get("metadata") or {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else utc_now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else utc_now(),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "parent_run_id": self.parent_run_id,
            "workflow_id": self.workflow_id,
            "session_id": self.session_id,
            "project_id": self.project_id,
            "task": self.task,
            "status": self.status.value,
            "workdir": self.workdir,
            "branch": self.branch,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass(frozen=True)
class StepRecord:
    """Durable metadata for one execution step inside a run."""

    run_id: str
    step_type: StepType
    step_id: str = field(default_factory=lambda: f"step_{uuid4().hex}")
    status: StepStatus = StepStatus.PENDING
    parent_step_id: str | None = None
    node_id: str | None = None
    agent_id: str | None = None
    input_ref: str | None = None
    output_ref: str | None = None
    error_ref: str | None = None
    checkpoint_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None
    ended_at: datetime | None = None

    def start(self) -> "StepRecord":
        return self._replace(status=StepStatus.RUNNING, started_at=utc_now())

    def complete(self, *, output_ref: str | None = None) -> "StepRecord":
        return self._replace(
            status=StepStatus.COMPLETED,
            output_ref=output_ref if output_ref is not None else self.output_ref,
            ended_at=utc_now(),
        )

    def wait(self, *, output_ref: str | None = None) -> "StepRecord":
        return self._replace(
            status=StepStatus.WAITING,
            output_ref=output_ref if output_ref is not None else self.output_ref,
        )

    def fail(self, *, error_ref: str | None = None) -> "StepRecord":
        return self._replace(
            status=StepStatus.FAILED,
            error_ref=error_ref if error_ref is not None else self.error_ref,
            ended_at=utc_now(),
        )

    def _replace(self, **changes: Any) -> "StepRecord":
        data = {
            "run_id": self.run_id,
            "step_type": self.step_type,
            "step_id": self.step_id,
            "status": self.status,
            "parent_step_id": self.parent_step_id,
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "input_ref": self.input_ref,
            "output_ref": self.output_ref,
            "error_ref": self.error_ref,
            "checkpoint_id": self.checkpoint_id,
            "metadata": dict(self.metadata),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }
        data.update(changes)
        return StepRecord(**data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StepRecord":
        return cls(
            step_id=data["step_id"],
            run_id=data["run_id"],
            parent_step_id=data.get("parent_step_id"),
            node_id=data.get("node_id"),
            agent_id=data.get("agent_id"),
            step_type=StepType(data["step_type"]),
            status=StepStatus(data.get("status", StepStatus.PENDING.value)),
            input_ref=data.get("input_ref"),
            output_ref=data.get("output_ref"),
            error_ref=data.get("error_ref"),
            checkpoint_id=data.get("checkpoint_id"),
            metadata=dict(data.get("metadata") or {}),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            ended_at=datetime.fromisoformat(data["ended_at"]) if data.get("ended_at") else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "run_id": self.run_id,
            "parent_step_id": self.parent_step_id,
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "step_type": self.step_type.value,
            "status": self.status.value,
            "input_ref": self.input_ref,
            "output_ref": self.output_ref,
            "error_ref": self.error_ref,
            "checkpoint_id": self.checkpoint_id,
            "metadata": self.metadata,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }
