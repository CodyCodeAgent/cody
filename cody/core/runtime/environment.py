"""Runtime environment factory for wiring stores and user-facing services."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
from typing import Any, cast

from .approval import InMemoryApprovalStore, SQLiteApprovalStore
from .artifact import InMemoryArtifactStore, SQLiteArtifactStore
from .audit import InMemoryRuntimeAuditStore, SQLiteRuntimeAuditStore
from .checkpoint import InMemoryCheckpointStore, SQLiteCheckpointStore
from .control import SQLiteWorkflowControlState, WorkflowControlState
from .interface import RuntimeInterface
from .object_storage import ObjectArtifactStore, ObjectStorage
from .postgres import (
    PostgresApprovalStore,
    PostgresArtifactStore,
    PostgresCheckpointStore,
    PostgresRunStore,
    PostgresRuntimeAuditStore,
    PostgresRuntimeDatabase,
    PostgresTraceStore,
    PostgresWorkflowControlState,
)
from .registry import InMemoryRunStore, SQLiteRunStore
from .security import RuntimeActionPolicy
from .trace import InMemoryTraceStore, SQLiteTraceStore


@dataclass(frozen=True)
class RuntimeStoreBundle:
    """Canonical bundle of runtime stores for local or durable deployments."""

    trace_store: InMemoryTraceStore | SQLiteTraceStore | PostgresTraceStore
    checkpoint_store: InMemoryCheckpointStore | SQLiteCheckpointStore | PostgresCheckpointStore
    artifact_store: InMemoryArtifactStore | SQLiteArtifactStore | PostgresArtifactStore | ObjectArtifactStore
    approval_store: InMemoryApprovalStore | SQLiteApprovalStore | PostgresApprovalStore
    run_store: InMemoryRunStore | SQLiteRunStore | PostgresRunStore
    audit_store: InMemoryRuntimeAuditStore | SQLiteRuntimeAuditStore | PostgresRuntimeAuditStore
    control_store: WorkflowControlState | SQLiteWorkflowControlState | PostgresWorkflowControlState

    @classmethod
    def in_memory(cls) -> "RuntimeStoreBundle":
        return cls(
            trace_store=InMemoryTraceStore(),
            checkpoint_store=InMemoryCheckpointStore(),
            artifact_store=InMemoryArtifactStore(),
            approval_store=InMemoryApprovalStore(),
            run_store=InMemoryRunStore(),
            audit_store=InMemoryRuntimeAuditStore(),
            control_store=WorkflowControlState(),
        )

    @classmethod
    def sqlite(
        cls,
        root: str | Path,
        *,
        object_storage: ObjectStorage | None = None,
    ) -> "RuntimeStoreBundle":
        root_path = Path(root)
        root_path.mkdir(parents=True, exist_ok=True)
        artifact_catalog = SQLiteArtifactStore(root_path / "artifact.sqlite3")
        return cls(
            trace_store=SQLiteTraceStore(root_path / "trace.sqlite3"),
            checkpoint_store=SQLiteCheckpointStore(root_path / "checkpoint.sqlite3"),
            artifact_store=(
                ObjectArtifactStore(artifact_catalog, object_storage)
                if object_storage is not None
                else artifact_catalog
            ),
            approval_store=SQLiteApprovalStore(root_path / "approval.sqlite3"),
            run_store=SQLiteRunStore(root_path / "run.sqlite3"),
            audit_store=SQLiteRuntimeAuditStore(root_path / "audit.sqlite3"),
            control_store=SQLiteWorkflowControlState(root_path / "control.sqlite3"),
        )

    @classmethod
    def for_workdir(
        cls,
        workdir: str | Path,
        *,
        base_dir: str | Path | None = None,
    ) -> "RuntimeStoreBundle":
        """Open the canonical durable stores shared by all product surfaces."""

        return cls.sqlite(runtime_root_for_workdir(workdir, base_dir=base_dir))

    @classmethod
    def postgres(
        cls,
        dsn: str,
        *,
        schema: str = "public",
        object_storage: ObjectStorage | None = None,
        connect=None,
    ) -> "RuntimeStoreBundle":
        """Build multi-process stores on one PostgreSQL JSONB catalog."""

        database = PostgresRuntimeDatabase(dsn, schema=schema, connect=connect)
        artifact_catalog = PostgresArtifactStore(database)
        return cls(
            trace_store=PostgresTraceStore(database),
            checkpoint_store=PostgresCheckpointStore(database),
            artifact_store=(
                ObjectArtifactStore(artifact_catalog, object_storage)
                if object_storage is not None
                else artifact_catalog
            ),
            approval_store=PostgresApprovalStore(database),
            run_store=PostgresRunStore(database),
            audit_store=PostgresRuntimeAuditStore(database),
            control_store=PostgresWorkflowControlState(database),
        )

    def interface(self, *, action_policy: RuntimeActionPolicy | None = None) -> RuntimeInterface:
        return RuntimeInterface(
            # Store backends are structurally compatible. The legacy concrete
            # constructor annotations have not yet been replaced by protocols.
            trace_store=cast(Any, self.trace_store),
            checkpoint_store=cast(Any, self.checkpoint_store),
            artifact_store=cast(Any, self.artifact_store),
            approval_store=cast(Any, self.approval_store),
            run_store=cast(Any, self.run_store),
            audit_store=cast(Any, self.audit_store),
            action_policy=action_policy,
            control_store=cast(Any, self.control_store),
        )


def runtime_root_for_workdir(
    workdir: str | Path,
    *,
    base_dir: str | Path | None = None,
) -> Path:
    """Return a stable per-project runtime root without polluting the project."""

    resolved = Path(workdir).expanduser().resolve()
    project_id = sha256(str(resolved).encode()).hexdigest()[:20]
    configured = os.environ.get("CODY_RUNTIME_HOME")
    root = (
        Path(base_dir).expanduser()
        if base_dir is not None
        else Path(configured).expanduser()
        if configured
        else Path.home() / ".cody" / "runtime"
    )
    return root / project_id
