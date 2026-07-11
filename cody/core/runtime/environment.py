"""Runtime environment factory for wiring stores and user-facing services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .approval import InMemoryApprovalStore, SQLiteApprovalStore
from .artifact import InMemoryArtifactStore, SQLiteArtifactStore
from .audit import InMemoryRuntimeAuditStore, SQLiteRuntimeAuditStore
from .checkpoint import InMemoryCheckpointStore, SQLiteCheckpointStore
from .interface import RuntimeInterface
from .registry import InMemoryRunStore, SQLiteRunStore
from .security import RuntimeActionPolicy
from .trace import InMemoryTraceStore, SQLiteTraceStore


@dataclass(frozen=True)
class RuntimeStoreBundle:
    """Canonical bundle of runtime stores for local or durable deployments."""

    trace_store: InMemoryTraceStore | SQLiteTraceStore
    checkpoint_store: InMemoryCheckpointStore | SQLiteCheckpointStore
    artifact_store: InMemoryArtifactStore | SQLiteArtifactStore
    approval_store: InMemoryApprovalStore | SQLiteApprovalStore
    run_store: InMemoryRunStore | SQLiteRunStore
    audit_store: InMemoryRuntimeAuditStore | SQLiteRuntimeAuditStore

    @classmethod
    def in_memory(cls) -> "RuntimeStoreBundle":
        return cls(
            trace_store=InMemoryTraceStore(),
            checkpoint_store=InMemoryCheckpointStore(),
            artifact_store=InMemoryArtifactStore(),
            approval_store=InMemoryApprovalStore(),
            run_store=InMemoryRunStore(),
            audit_store=InMemoryRuntimeAuditStore(),
        )

    @classmethod
    def sqlite(cls, root: str | Path) -> "RuntimeStoreBundle":
        root_path = Path(root)
        root_path.mkdir(parents=True, exist_ok=True)
        return cls(
            trace_store=SQLiteTraceStore(root_path / "trace.sqlite3"),
            checkpoint_store=SQLiteCheckpointStore(root_path / "checkpoint.sqlite3"),
            artifact_store=SQLiteArtifactStore(root_path / "artifact.sqlite3"),
            approval_store=SQLiteApprovalStore(root_path / "approval.sqlite3"),
            run_store=SQLiteRunStore(root_path / "run.sqlite3"),
            audit_store=SQLiteRuntimeAuditStore(root_path / "audit.sqlite3"),
        )

    def interface(self, *, action_policy: RuntimeActionPolicy | None = None) -> RuntimeInterface:
        return RuntimeInterface(
            trace_store=self.trace_store,
            checkpoint_store=self.checkpoint_store,
            artifact_store=self.artifact_store,
            approval_store=self.approval_store,
            run_store=self.run_store,
            audit_store=self.audit_store,
            action_policy=action_policy,
        )
