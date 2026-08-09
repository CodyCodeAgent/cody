"""Durable approval requests for human-in-the-loop workflows."""

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


class ApprovalStatus(str, Enum):
    """Lifecycle states for durable approval requests."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ApprovalRequestRecord:
    """Durable human approval request linked to a workflow run/node."""

    run_id: str
    node_id: str
    request: dict[str, Any]
    approval_id: str = field(default_factory=lambda: f"approval_{uuid4().hex}")
    status: ApprovalStatus = ApprovalStatus.PENDING
    response: dict[str, Any] = field(default_factory=dict)
    requested_by: str | None = None
    assigned_to: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    resolved_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def approve(self, response: dict[str, Any] | None = None) -> "ApprovalRequestRecord":
        return self._transition(ApprovalStatus.APPROVED, response=response or {"approved": True})

    def reject(self, response: dict[str, Any] | None = None) -> "ApprovalRequestRecord":
        return self._transition(ApprovalStatus.REJECTED, response=response or {"approved": False})

    def expire(self, response: dict[str, Any] | None = None) -> "ApprovalRequestRecord":
        return self._transition(ApprovalStatus.EXPIRED, response=response or {})

    def _transition(self, status: ApprovalStatus, *, response: dict[str, Any]) -> "ApprovalRequestRecord":
        now = _utc_now()
        return ApprovalRequestRecord(
            run_id=self.run_id,
            node_id=self.node_id,
            request=dict(self.request),
            approval_id=self.approval_id,
            status=status,
            response=dict(response),
            requested_by=self.requested_by,
            assigned_to=self.assigned_to,
            created_at=self.created_at,
            updated_at=now,
            resolved_at=now,
            metadata=dict(self.metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "request": self.request,
            "status": self.status.value,
            "response": self.response,
            "requested_by": self.requested_by,
            "assigned_to": self.assigned_to,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalRequestRecord":
        return cls(
            approval_id=data.get("approval_id") or f"approval_{uuid4().hex}",
            run_id=data["run_id"],
            node_id=data["node_id"],
            request=dict(data.get("request") or {}),
            status=ApprovalStatus(data.get("status", ApprovalStatus.PENDING.value)),
            response=dict(data.get("response") or {}),
            requested_by=data.get("requested_by"),
            assigned_to=data.get("assigned_to"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else _utc_now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else _utc_now(),
            resolved_at=datetime.fromisoformat(data["resolved_at"]) if data.get("resolved_at") else None,
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class InMemoryApprovalStore:
    """In-memory approval request store."""

    _approvals: dict[str, ApprovalRequestRecord] = field(default_factory=dict)
    _by_run: dict[str, list[str]] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock, repr=False)

    def save(self, approval: ApprovalRequestRecord) -> ApprovalRequestRecord:
        with self._lock:
            if approval.approval_id not in self._approvals:
                self._by_run.setdefault(approval.run_id, []).append(approval.approval_id)
            self._approvals[approval.approval_id] = approval
        return approval

    def get(self, approval_id: str) -> ApprovalRequestRecord | None:
        with self._lock:
            return self._approvals.get(approval_id)

    def list(self, *, run_id: str | None = None, status: ApprovalStatus | None = None) -> list[ApprovalRequestRecord]:
        with self._lock:
            if run_id is None:
                approvals = list(self._approvals.values())
            else:
                approvals = [self._approvals[approval_id] for approval_id in self._by_run.get(run_id, [])]
        if status is not None:
            return [approval for approval in approvals if approval.status == status]
        return approvals

    def approve(self, approval_id: str, response: dict[str, Any] | None = None) -> ApprovalRequestRecord:
        approval = self.get(approval_id)
        if approval is None:
            raise KeyError(f"Approval not found: {approval_id}")
        return self.save(approval.approve(response))

    def reject(self, approval_id: str, response: dict[str, Any] | None = None) -> ApprovalRequestRecord:
        approval = self.get(approval_id)
        if approval is None:
            raise KeyError(f"Approval not found: {approval_id}")
        return self.save(approval.reject(response))


class SQLiteApprovalStore:
    """SQLite-backed approval request store."""

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
                CREATE TABLE IF NOT EXISTS runtime_approvals (
                    approval_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    approval_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runtime_approvals_run_status "
                "ON runtime_approvals(run_id, status)"
            )

    def save(self, approval: ApprovalRequestRecord) -> ApprovalRequestRecord:
        data = approval.to_dict()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runtime_approvals (
                    approval_id, run_id, node_id, status, updated_at, approval_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    data["approval_id"],
                    data["run_id"],
                    data["node_id"],
                    data["status"],
                    data["updated_at"],
                    json.dumps(data, sort_keys=True),
                ),
            )
        return approval

    def get(self, approval_id: str) -> ApprovalRequestRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT approval_json FROM runtime_approvals WHERE approval_id = ?", (approval_id,)).fetchone()
        if row is None:
            return None
        return ApprovalRequestRecord.from_dict(json.loads(row["approval_json"]))

    def list(self, *, run_id: str | None = None, status: ApprovalStatus | None = None) -> list[ApprovalRequestRecord]:
        query = "SELECT approval_json FROM runtime_approvals"
        params: list[str] = []
        clauses = []
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at ASC"
        with self._lock, self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [ApprovalRequestRecord.from_dict(json.loads(row["approval_json"])) for row in rows]

    def approve(self, approval_id: str, response: dict[str, Any] | None = None) -> ApprovalRequestRecord:
        approval = self.get(approval_id)
        if approval is None:
            raise KeyError(f"Approval not found: {approval_id}")
        return self.save(approval.approve(response))

    def reject(self, approval_id: str, response: dict[str, Any] | None = None) -> ApprovalRequestRecord:
        approval = self.get(approval_id)
        if approval is None:
            raise KeyError(f"Approval not found: {approval_id}")
        return self.save(approval.reject(response))
