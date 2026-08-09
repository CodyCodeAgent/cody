"""Artifact storage primitives for runtime outputs and reviewable assets."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4
import json
import sqlite3


class ArtifactType(str, Enum):
    """Common artifact categories produced by workflows."""

    PLAN = "plan"
    DIFF = "diff"
    TEST_REPORT = "test_report"
    REVIEW = "review"
    APPROVAL = "approval"
    CONTEXT_PACK = "context_pack"
    TOOL_OUTPUT = "tool_output"
    SANDBOX_SNAPSHOT = "sandbox_snapshot"
    GENERIC = "generic"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ArtifactRecord:
    """Durable artifact linked to a run, step, checkpoint, or event."""

    run_id: str
    artifact_type: ArtifactType
    content: dict[str, Any] | str
    artifact_id: str = field(default_factory=lambda: f"artifact_{uuid4().hex}")
    step_id: str | None = None
    checkpoint_id: str | None = None
    event_id: str | None = None
    name: str | None = None
    mime_type: str = "application/json"
    metadata: dict[str, Any] = field(default_factory=dict)
    parent_artifact_id: str | None = None
    created_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "parent_artifact_id": self.parent_artifact_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "checkpoint_id": self.checkpoint_id,
            "event_id": self.event_id,
            "artifact_type": self.artifact_type.value,
            "name": self.name,
            "mime_type": self.mime_type,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactRecord":
        raw_content = data.get("content", {})
        content: dict[str, Any] | str = (
            raw_content if isinstance(raw_content, (dict, str)) else {}
        )
        return cls(
            artifact_id=data.get("artifact_id") or f"artifact_{uuid4().hex}",
            parent_artifact_id=data.get("parent_artifact_id"),
            run_id=data["run_id"],
            step_id=data.get("step_id"),
            checkpoint_id=data.get("checkpoint_id"),
            event_id=data.get("event_id"),
            artifact_type=ArtifactType(data.get("artifact_type", ArtifactType.GENERIC.value)),
            name=data.get("name"),
            mime_type=data.get("mime_type") or "application/json",
            content=content,
            metadata=dict(data.get("metadata") or {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else _utc_now(),
        )


@dataclass
class InMemoryArtifactStore:
    """In-memory artifact store for tests and local workflows."""

    _artifacts: dict[str, ArtifactRecord] = field(default_factory=dict)
    _by_run: dict[str, list[str]] = field(default_factory=dict)
    _by_step: dict[str, list[str]] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock, repr=False)

    def save(self, artifact: ArtifactRecord) -> ArtifactRecord:
        with self._lock:
            if artifact.artifact_id not in self._artifacts:
                self._by_run.setdefault(artifact.run_id, []).append(artifact.artifact_id)
                if artifact.step_id:
                    self._by_step.setdefault(artifact.step_id, []).append(artifact.artifact_id)
            self._artifacts[artifact.artifact_id] = artifact
        return artifact

    def get(self, artifact_id: str) -> ArtifactRecord | None:
        with self._lock:
            return self._artifacts.get(artifact_id)

    def list(self, *, run_id: str | None = None, step_id: str | None = None, artifact_type: ArtifactType | None = None) -> list[ArtifactRecord]:
        with self._lock:
            if step_id is not None:
                artifacts = [self._artifacts[artifact_id] for artifact_id in self._by_step.get(step_id, [])]
            elif run_id is not None:
                artifacts = [self._artifacts[artifact_id] for artifact_id in self._by_run.get(run_id, [])]
            else:
                artifacts = list(self._artifacts.values())
        if artifact_type is not None:
            return [artifact for artifact in artifacts if artifact.artifact_type == artifact_type]
        return artifacts


class SQLiteArtifactStore:
    """SQLite-backed artifact store."""

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
                CREATE TABLE IF NOT EXISTS runtime_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    parent_artifact_id TEXT,
                    run_id TEXT NOT NULL,
                    step_id TEXT,
                    checkpoint_id TEXT,
                    event_id TEXT,
                    artifact_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    artifact_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runtime_artifacts_run_type "
                "ON runtime_artifacts(run_id, artifact_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runtime_artifacts_step "
                "ON runtime_artifacts(step_id)"
            )

    def save(self, artifact: ArtifactRecord) -> ArtifactRecord:
        data = artifact.to_dict()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runtime_artifacts (
                    artifact_id, parent_artifact_id, run_id, step_id, checkpoint_id,
                    event_id, artifact_type, created_at, artifact_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["artifact_id"],
                    data["parent_artifact_id"],
                    data["run_id"],
                    data["step_id"],
                    data["checkpoint_id"],
                    data["event_id"],
                    data["artifact_type"],
                    data["created_at"],
                    json.dumps(data, sort_keys=True),
                ),
            )
        return artifact

    def get(self, artifact_id: str) -> ArtifactRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT artifact_json FROM runtime_artifacts WHERE artifact_id = ?", (artifact_id,)).fetchone()
        if row is None:
            return None
        return ArtifactRecord.from_dict(json.loads(row["artifact_json"]))

    def list(self, *, run_id: str | None = None, step_id: str | None = None, artifact_type: ArtifactType | None = None) -> list[ArtifactRecord]:
        query = "SELECT artifact_json FROM runtime_artifacts"
        params: list[str] = []
        clauses = []
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        if step_id is not None:
            clauses.append("step_id = ?")
            params.append(step_id)
        if artifact_type is not None:
            clauses.append("artifact_type = ?")
            params.append(artifact_type.value)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at ASC"
        with self._lock, self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [ArtifactRecord.from_dict(json.loads(row["artifact_json"])) for row in rows]
