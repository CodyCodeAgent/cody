"""Audit logging for Cody operations"""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class AuditEvent(str, Enum):
    """Auditable event types."""
    TOOL_CALL = "tool_call"
    FILE_WRITE = "file_write"
    FILE_EDIT = "file_edit"
    COMMAND_EXEC = "command_exec"
    API_REQUEST = "api_request"
    AUTH_LOGIN = "auth_login"
    AUTH_FAILURE = "auth_failure"
    PERMISSION_DENIED = "permission_denied"


@dataclass
class AuditEntry:
    """A single audit log entry."""
    id: str
    timestamp: str
    event: str
    tool_name: Optional[str]
    args_summary: Optional[str]
    result_summary: Optional[str]
    session_id: Optional[str]
    workdir: Optional[str]
    success: bool


def _truncate(s: str, max_len: int) -> str:
    """Truncate string to max_len, appending '...' if truncated."""
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


class AuditLogger:
    """SQLite-backed audit logger."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path.home() / ".cody" / "audit.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._init_db()
        # Reuse the connection created during _init_db (or create fresh)
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        return self._conn

    def close(self) -> None:
        """Close the persistent database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __del__(self):
        self.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    event TEXT NOT NULL,
                    tool_name TEXT,
                    args_summary TEXT,
                    result_summary TEXT,
                    session_id TEXT,
                    workdir TEXT,
                    success INTEGER NOT NULL DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp
                ON audit_log(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_event
                ON audit_log(event)
            """)

    def log(
        self,
        event: str,
        tool_name: Optional[str] = None,
        args_summary: Optional[str] = None,
        result_summary: Optional[str] = None,
        session_id: Optional[str] = None,
        workdir: Optional[str] = None,
        success: bool = True,
    ) -> AuditEntry:
        """Record an audit event."""
        entry = AuditEntry(
            id=uuid.uuid4().hex[:12],
            timestamp=datetime.now(timezone.utc).isoformat(),
            event=event,
            tool_name=tool_name,
            args_summary=_truncate(args_summary, 500) if args_summary else None,
            result_summary=_truncate(result_summary, 500) if result_summary else None,
            session_id=session_id,
            workdir=workdir,
            success=success,
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO audit_log "
                "(id, timestamp, event, tool_name, args_summary, result_summary, "
                "session_id, workdir, success) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.id,
                    entry.timestamp,
                    entry.event,
                    entry.tool_name,
                    entry.args_summary,
                    entry.result_summary,
                    entry.session_id,
                    entry.workdir,
                    1 if entry.success else 0,
                ),
            )
        return entry

    def query(
        self,
        event: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 50,
    ) -> list[AuditEntry]:
        """Query audit entries with optional filters."""
        sql = (
            "SELECT id, timestamp, event, tool_name, args_summary, "
            "result_summary, session_id, workdir, success FROM audit_log"
        )
        conditions: list[str] = []
        params: list[Any] = []

        if event:
            conditions.append("event = ?")
            params.append(event)
        if since:
            conditions.append("timestamp >= ?")
            params.append(since)

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [
            AuditEntry(
                id=r[0],
                timestamp=r[1],
                event=r[2],
                tool_name=r[3],
                args_summary=r[4],
                result_summary=r[5],
                session_id=r[6],
                workdir=r[7],
                success=bool(r[8]),
            )
            for r in rows
        ]

    def count(self, event: Optional[str] = None) -> int:
        """Count audit entries, optionally filtered by event type."""
        if event:
            sql = "SELECT COUNT(*) FROM audit_log WHERE event = ?"
            params: tuple = (event,)
        else:
            sql = "SELECT COUNT(*) FROM audit_log"
            params = ()

        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return row[0] if row else 0

    def clear(self, before: Optional[str] = None) -> int:
        """Clear audit log entries. If before is given, only clear older entries."""
        if before:
            sql = "DELETE FROM audit_log WHERE timestamp < ?"
            params: tuple = (before,)
        else:
            sql = "DELETE FROM audit_log"
            params = ()

        with self._connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.rowcount
