"""PostgreSQL stores for multi-process Runtime deployments.

All record types share one indexed JSONB catalog.  Typed adapters retain the
same synchronous contracts as the local SQLite stores, so schedulers and
product surfaces do not depend on a database-specific execution path.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from .approval import ApprovalRequestRecord, ApprovalStatus
from .artifact import ArtifactRecord, ArtifactType
from .audit import RuntimeAuditRecord
from .checkpoint import CheckpointRecord
from .events import RunEvent
from .models import RunRecord, RunStatus, StepRecord


class PostgresRuntimeDatabase:
    """Shared JSONB catalog and connection factory for typed Runtime stores."""

    def __init__(
        self,
        dsn: str,
        *,
        schema: str = "public",
        connect: Callable[[], Any] | None = None,
    ):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
            raise ValueError(f"Invalid PostgreSQL schema: {schema}")
        self.dsn = dsn
        self.schema = schema
        self.table = f'"{schema}"."cody_runtime_records"'
        self._connect_factory = connect
        self._initialize()

    def connect(self):
        if self._connect_factory is not None:
            return self._connect_factory()
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "Install cody-ai[production] to use PostgreSQL Runtime stores"
            ) from exc
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def _initialize(self) -> None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table} (
                    kind TEXT NOT NULL,
                    record_key TEXT NOT NULL,
                    run_id TEXT,
                    status TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    data JSONB NOT NULL,
                    PRIMARY KEY (kind, record_key)
                )
                """
            )
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS cody_runtime_kind_run_idx "
                f"ON {self.table} (kind, run_id, created_at)"
            )
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS cody_runtime_kind_status_idx "
                f"ON {self.table} (kind, status, updated_at)"
            )

    def upsert(
        self,
        kind: str,
        key: str,
        data: dict[str, Any],
        *,
        run_id: str | None = None,
        status: str | None = None,
    ) -> None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {self.table} (kind, record_key, run_id, status, data)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (kind, record_key) DO UPDATE SET
                    run_id = EXCLUDED.run_id,
                    status = EXCLUDED.status,
                    data = EXCLUDED.data,
                    updated_at = NOW()
                """,
                (kind, key, run_id, status, json.dumps(data)),
            )

    def get(self, kind: str, key: str) -> dict[str, Any] | None:
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT data FROM {self.table} WHERE kind = %s AND record_key = %s",
                (kind, key),
            )
            row = cursor.fetchone()
        return self._data(row) if row is not None else None

    def mutate(
        self,
        kind: str,
        key: str,
        updater: Callable[[dict[str, Any] | None], dict[str, Any]],
        *,
        run_id: str | None = None,
        status: Callable[[dict[str, Any]], str | None] | None = None,
    ) -> dict[str, Any]:
        """Atomically lock, update, and upsert one record."""

        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT data FROM {self.table} WHERE kind = %s AND record_key = %s FOR UPDATE",
                (kind, key),
            )
            row = cursor.fetchone()
            current = self._data(row) if row is not None else None
            updated = updater(current)
            record_status = status(updated) if status is not None else None
            cursor.execute(
                f"""
                INSERT INTO {self.table} (kind, record_key, run_id, status, data)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (kind, record_key) DO UPDATE SET
                    run_id = COALESCE(EXCLUDED.run_id, {self.table}.run_id),
                    status = EXCLUDED.status,
                    data = EXCLUDED.data, updated_at = NOW()
                """,
                (kind, key, run_id, record_status, json.dumps(updated)),
            )
        return updated

    def list(
        self,
        kind: str,
        *,
        run_id: str | None = None,
        status: str | None = None,
        newest_first: bool = False,
    ) -> list[dict[str, Any]]:
        clauses = ["kind = %s"]
        params: list[Any] = [kind]
        if run_id is not None:
            clauses.append("run_id = %s")
            params.append(run_id)
        if status is not None:
            clauses.append("status = %s")
            params.append(status)
        direction = "DESC" if newest_first else "ASC"
        with self.connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT data FROM {self.table} WHERE {' AND '.join(clauses)} "
                f"ORDER BY created_at {direction}, record_key {direction}",
                tuple(params),
            )
            rows = cursor.fetchall()
        return [self._data(row) for row in rows]

    @staticmethod
    def _data(row: Any) -> dict[str, Any]:
        value = row["data"] if isinstance(row, dict) else row[0]
        return json.loads(value) if isinstance(value, str) else dict(value)


class PostgresRunStore:
    def __init__(self, database: PostgresRuntimeDatabase):
        self.db = database

    def save_run(self, run: RunRecord) -> RunRecord:
        self.db.upsert("run", run.run_id, run.to_dict(), run_id=run.run_id, status=run.status.value)
        return run

    def get_run(self, run_id: str) -> RunRecord | None:
        data = self.db.get("run", run_id)
        return RunRecord.from_dict(data) if data else None

    def list_runs(self, *, status: RunStatus | None = None) -> list[RunRecord]:
        return [
            RunRecord.from_dict(item)
            for item in self.db.list("run", status=status.value if status else None)
        ]

    def save_step(self, step: StepRecord) -> StepRecord:
        self.db.upsert(
            "step", step.step_id, step.to_dict(), run_id=step.run_id, status=step.status.value
        )
        return step

    def get_step(self, step_id: str) -> StepRecord | None:
        data = self.db.get("step", step_id)
        return StepRecord.from_dict(data) if data else None

    def list_steps(self, run_id: str) -> list[StepRecord]:
        return [StepRecord.from_dict(item) for item in self.db.list("step", run_id=run_id)]


class PostgresTraceStore:
    def __init__(self, database: PostgresRuntimeDatabase):
        self.db = database

    def append(self, event: RunEvent) -> RunEvent:
        self.db.upsert("event", event.event_id, event.to_dict(), run_id=event.run_id)
        return event

    def extend(self, events: list[RunEvent]) -> list[RunEvent]:
        for event in events:
            self.append(event)
        return events

    def list_events(self, run_id: str | None = None) -> list[RunEvent]:
        return [RunEvent.from_dict(item) for item in self.db.list("event", run_id=run_id)]

    def export_jsonl(self, run_id: str | None = None) -> str:
        return "\n".join(
            json.dumps(event.to_dict(), sort_keys=True) for event in self.list_events(run_id)
        )


class PostgresCheckpointStore:
    def __init__(self, database: PostgresRuntimeDatabase):
        self.db = database

    def save(self, checkpoint: CheckpointRecord) -> CheckpointRecord:
        self.db.upsert(
            "checkpoint", checkpoint.checkpoint_id, checkpoint.to_dict(), run_id=checkpoint.run_id
        )
        return checkpoint

    def list_checkpoints(self, run_id: str | None = None) -> list[CheckpointRecord]:
        return [
            CheckpointRecord.from_dict(item) for item in self.db.list("checkpoint", run_id=run_id)
        ]

    def latest(self, run_id: str) -> CheckpointRecord | None:
        items = self.db.list("checkpoint", run_id=run_id, newest_first=True)
        return CheckpointRecord.from_dict(items[0]) if items else None

    def get(self, checkpoint_id: str) -> CheckpointRecord | None:
        data = self.db.get("checkpoint", checkpoint_id)
        return CheckpointRecord.from_dict(data) if data else None


class PostgresArtifactStore:
    def __init__(self, database: PostgresRuntimeDatabase):
        self.db = database

    def save(self, artifact: ArtifactRecord) -> ArtifactRecord:
        self.db.upsert(
            "artifact",
            artifact.artifact_id,
            artifact.to_dict(),
            run_id=artifact.run_id,
            status=artifact.artifact_type.value,
        )
        return artifact

    def get(self, artifact_id: str) -> ArtifactRecord | None:
        data = self.db.get("artifact", artifact_id)
        return ArtifactRecord.from_dict(data) if data else None

    def list(
        self,
        *,
        run_id: str | None = None,
        step_id: str | None = None,
        artifact_type: ArtifactType | None = None,
    ) -> list[ArtifactRecord]:
        records = [
            ArtifactRecord.from_dict(item)
            for item in self.db.list(
                "artifact", run_id=run_id, status=artifact_type.value if artifact_type else None
            )
        ]
        return [record for record in records if step_id is None or record.step_id == step_id]


class PostgresApprovalStore:
    def __init__(self, database: PostgresRuntimeDatabase):
        self.db = database

    def save(self, approval: ApprovalRequestRecord) -> ApprovalRequestRecord:
        self.db.upsert(
            "approval",
            approval.approval_id,
            approval.to_dict(),
            run_id=approval.run_id,
            status=approval.status.value,
        )
        return approval

    def get(self, approval_id: str) -> ApprovalRequestRecord | None:
        data = self.db.get("approval", approval_id)
        return ApprovalRequestRecord.from_dict(data) if data else None

    def list(
        self, *, run_id: str | None = None, status: ApprovalStatus | None = None
    ) -> list[ApprovalRequestRecord]:
        return [
            ApprovalRequestRecord.from_dict(item)
            for item in self.db.list(
                "approval", run_id=run_id, status=status.value if status else None
            )
        ]

    def approve(
        self, approval_id: str, response: dict[str, Any] | None = None
    ) -> ApprovalRequestRecord:
        return self._transition(approval_id, "approve", response)

    def reject(
        self, approval_id: str, response: dict[str, Any] | None = None
    ) -> ApprovalRequestRecord:
        return self._transition(approval_id, "reject", response)

    def _transition(
        self, approval_id: str, action: str, response: dict[str, Any] | None
    ) -> ApprovalRequestRecord:
        def update(data):
            if data is None:
                raise KeyError(f"Approval not found: {approval_id}")
            approval = ApprovalRequestRecord.from_dict(data)
            return getattr(approval, action)(response).to_dict()

        data = self.db.mutate(
            "approval",
            approval_id,
            update,
            status=lambda item: item.get("status"),
        )
        return ApprovalRequestRecord.from_dict(data)


class PostgresRuntimeAuditStore:
    def __init__(self, database: PostgresRuntimeDatabase):
        self.db = database

    def append(self, record: RuntimeAuditRecord) -> RuntimeAuditRecord:
        self.db.upsert(
            "audit", record.audit_id, record.to_dict(), run_id=record.run_id, status=record.action
        )
        return record

    def list(
        self, *, actor_id: str | None = None, action: str | None = None
    ) -> list[RuntimeAuditRecord]:
        records = [
            RuntimeAuditRecord.from_dict(item) for item in self.db.list("audit", status=action)
        ]
        return [record for record in records if actor_id is None or record.actor_id == actor_id]


class PostgresWorkflowControlState:
    def __init__(self, database: PostgresRuntimeDatabase):
        self.db = database

    def _read(self, run_id: str) -> dict[str, Any]:
        return self.db.get("control", run_id) or {}

    def _change(self, run_id: str, values: dict[str, Any]) -> None:
        self.db.mutate(
            "control",
            run_id,
            lambda current: {**(current or {}), **values},
            run_id=run_id,
        )

    def request_pause(self, run_id: str, *, before_node_id: str | None = None) -> None:
        self._change(run_id, {"pause": True, "pause_before": before_node_id})

    def clear_pause(self, run_id: str) -> None:
        self._change(run_id, {"pause": False, "pause_before": None})

    def request_cancel(self, run_id: str, *, before_node_id: str | None = None) -> None:
        self._change(run_id, {"cancel": True, "cancel_before": before_node_id})

    def clear_cancel(self, run_id: str) -> None:
        self._change(run_id, {"cancel": False, "cancel_before": None})

    def should_pause(self, run_id: str, node_id: str | None = None) -> bool:
        data = self._read(run_id)
        return bool(
            data.get("pause")
            and (not data.get("pause_before") or data.get("pause_before") == node_id)
        )

    def should_cancel(self, run_id: str, node_id: str | None = None) -> bool:
        data = self._read(run_id)
        return bool(
            data.get("cancel")
            and (not data.get("cancel_before") or data.get("cancel_before") == node_id)
        )
