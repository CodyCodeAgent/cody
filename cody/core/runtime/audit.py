"""Runtime audit records and stores."""

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
class RuntimeAuditRecord:
    """Append-only audit record for user-facing runtime actions."""

    action: str
    actor_id: str | None = None
    ok: bool = False
    effect: str = "read"
    run_id: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    audit_id: str = field(default_factory=lambda: f"audit_{uuid4().hex}")
    created_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "action": self.action,
            "actor_id": self.actor_id,
            "ok": self.ok,
            "effect": self.effect,
            "run_id": self.run_id,
            "error": self.error,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeAuditRecord":
        return cls(
            audit_id=data.get("audit_id") or f"audit_{uuid4().hex}",
            action=data["action"],
            actor_id=data.get("actor_id"),
            ok=bool(data.get("ok")),
            effect=data.get("effect", "read"),
            run_id=data.get("run_id"),
            error=data.get("error"),
            metadata=dict(data.get("metadata") or {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else _utc_now(),
        )


@dataclass
class InMemoryRuntimeAuditStore:
    """In-memory runtime audit store."""

    _records: list[RuntimeAuditRecord] = field(default_factory=list)
    _lock: RLock = field(default_factory=RLock, repr=False)

    def append(self, record: RuntimeAuditRecord) -> RuntimeAuditRecord:
        with self._lock:
            self._records.append(record)
        return record

    def list(self, *, actor_id: str | None = None, action: str | None = None) -> list[RuntimeAuditRecord]:
        with self._lock:
            records = list(self._records)
        if actor_id is not None:
            records = [record for record in records if record.actor_id == actor_id]
        if action is not None:
            records = [record for record in records if record.action == action]
        return records


class SQLiteRuntimeAuditStore:
    """SQLite-backed runtime audit store."""

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
                CREATE TABLE IF NOT EXISTS runtime_audit (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    audit_id TEXT NOT NULL UNIQUE,
                    actor_id TEXT,
                    action TEXT NOT NULL,
                    ok INTEGER NOT NULL,
                    effect TEXT NOT NULL,
                    run_id TEXT,
                    created_at TEXT NOT NULL,
                    audit_json TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_audit_actor_seq ON runtime_audit(actor_id, seq)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_audit_action_seq ON runtime_audit(action, seq)")

    def append(self, record: RuntimeAuditRecord) -> RuntimeAuditRecord:
        data = record.to_dict()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runtime_audit (
                    audit_id, actor_id, action, ok, effect, run_id, created_at, audit_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["audit_id"],
                    data["actor_id"],
                    data["action"],
                    int(data["ok"]),
                    data["effect"],
                    data["run_id"],
                    data["created_at"],
                    json.dumps(data, sort_keys=True),
                ),
            )
        return record

    def list(self, *, actor_id: str | None = None, action: str | None = None) -> list[RuntimeAuditRecord]:
        query = "SELECT audit_json FROM runtime_audit"
        clauses = []
        params: list[str] = []
        if actor_id is not None:
            clauses.append("actor_id = ?")
            params.append(actor_id)
        if action is not None:
            clauses.append("action = ?")
            params.append(action)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY seq ASC"
        with self._lock, self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [RuntimeAuditRecord.from_dict(json.loads(row["audit_json"])) for row in rows]
