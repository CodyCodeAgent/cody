"""Checkpoint records and stores for durable runtime recovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4
import json
import sqlite3


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CheckpointRecord:
    """Durable state snapshot for one run/step boundary.

    Checkpoints intentionally keep state as JSON-compatible dictionaries/lists so
    workflow, message, artifact, child-agent, and approval state can evolve
    without forcing schema migrations for every new runtime feature.
    """

    run_id: str
    step_id: str
    workflow_state: dict[str, Any] = field(default_factory=dict)
    message_state: list[dict[str, Any]] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    file_refs: list[str] = field(default_factory=list)
    child_run_ids: list[str] = field(default_factory=list)
    pending_approval_ids: list[str] = field(default_factory=list)
    budget_state: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    checkpoint_id: str = field(default_factory=lambda: f"ckpt_{uuid4().hex}")
    parent_checkpoint_id: str | None = None
    created_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "parent_checkpoint_id": self.parent_checkpoint_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "workflow_state": self.workflow_state,
            "message_state": self.message_state,
            "artifact_refs": self.artifact_refs,
            "file_refs": self.file_refs,
            "child_run_ids": self.child_run_ids,
            "pending_approval_ids": self.pending_approval_ids,
            "budget_state": self.budget_state,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CheckpointRecord":
        return cls(
            checkpoint_id=data.get("checkpoint_id") or f"ckpt_{uuid4().hex}",
            parent_checkpoint_id=data.get("parent_checkpoint_id"),
            run_id=data["run_id"],
            step_id=data["step_id"],
            workflow_state=dict(data.get("workflow_state") or {}),
            message_state=list(data.get("message_state") or []),
            artifact_refs=list(data.get("artifact_refs") or []),
            file_refs=list(data.get("file_refs") or []),
            child_run_ids=list(data.get("child_run_ids") or []),
            pending_approval_ids=list(data.get("pending_approval_ids") or []),
            budget_state=dict(data.get("budget_state") or {}),
            metadata=dict(data.get("metadata") or {}),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else _utc_now()
            ),
        )


@dataclass
class InMemoryCheckpointStore:
    """In-memory checkpoint store for tests and ephemeral local runs."""

    _checkpoints: list[CheckpointRecord] = field(default_factory=list)
    _by_run: dict[str, list[CheckpointRecord]] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock, repr=False)

    def save(self, checkpoint: CheckpointRecord) -> CheckpointRecord:
        with self._lock:
            self._checkpoints.append(checkpoint)
            self._by_run.setdefault(checkpoint.run_id, []).append(checkpoint)
        return checkpoint

    def list_checkpoints(self, run_id: str | None = None) -> list[CheckpointRecord]:
        with self._lock:
            if run_id is None:
                return list(self._checkpoints)
            return list(self._by_run.get(run_id, []))

    def latest(self, run_id: str) -> CheckpointRecord | None:
        checkpoints = self.list_checkpoints(run_id)
        return checkpoints[-1] if checkpoints else None

    def get(self, checkpoint_id: str) -> CheckpointRecord | None:
        with self._lock:
            for checkpoint in self._checkpoints:
                if checkpoint.checkpoint_id == checkpoint_id:
                    return checkpoint
        return None


class SQLiteCheckpointStore:
    """SQLite-backed checkpoint store for durable recovery."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_checkpoints (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    checkpoint_id TEXT NOT NULL UNIQUE,
                    parent_checkpoint_id TEXT,
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    checkpoint_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runtime_checkpoints_run_seq "
                "ON runtime_checkpoints(run_id, seq)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runtime_checkpoints_step "
                "ON runtime_checkpoints(step_id)"
            )

    def save(self, checkpoint: CheckpointRecord) -> CheckpointRecord:
        data = checkpoint.to_dict()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runtime_checkpoints (
                    checkpoint_id, parent_checkpoint_id, run_id, step_id,
                    created_at, checkpoint_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    data["checkpoint_id"],
                    data["parent_checkpoint_id"],
                    data["run_id"],
                    data["step_id"],
                    data["created_at"],
                    json.dumps(data, sort_keys=True),
                ),
            )
        return checkpoint

    def list_checkpoints(self, run_id: str | None = None) -> list[CheckpointRecord]:
        query = "SELECT checkpoint_json FROM runtime_checkpoints"
        params: tuple[str, ...] = ()
        if run_id is not None:
            query += " WHERE run_id = ?"
            params = (run_id,)
        query += " ORDER BY seq ASC"

        with self._lock, self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [CheckpointRecord.from_dict(json.loads(row["checkpoint_json"])) for row in rows]

    def latest(self, run_id: str) -> CheckpointRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT checkpoint_json FROM runtime_checkpoints
                WHERE run_id = ?
                ORDER BY seq DESC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return CheckpointRecord.from_dict(json.loads(row["checkpoint_json"]))

    def get(self, checkpoint_id: str) -> CheckpointRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT checkpoint_json FROM runtime_checkpoints WHERE checkpoint_id = ?",
                (checkpoint_id,),
            ).fetchone()
        if row is None:
            return None
        return CheckpointRecord.from_dict(json.loads(row["checkpoint_json"]))
