"""Workflow control signals for pause/cancel orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import sqlite3
from threading import RLock


class WorkflowPaused(RuntimeError):
    """Raised internally when a workflow pauses at a node boundary."""


class WorkflowCancelled(RuntimeError):
    """Raised internally when a workflow is cancelled at a node boundary."""


class WorkflowWaiting(RuntimeError):
    """Raised internally when a workflow waits for an external result."""


@dataclass
class WorkflowControlState:
    """Thread-safe control flags checked by workflow executors at node boundaries."""

    _paused_runs: set[str] = field(default_factory=set)
    _cancelled_runs: set[str] = field(default_factory=set)
    _pause_before_nodes: dict[str, set[str]] = field(default_factory=dict)
    _cancel_before_nodes: dict[str, set[str]] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock, repr=False)

    def request_pause(self, run_id: str, *, before_node_id: str | None = None) -> None:
        with self._lock:
            if before_node_id is None:
                self._paused_runs.add(run_id)
            else:
                self._pause_before_nodes.setdefault(run_id, set()).add(before_node_id)

    def clear_pause(self, run_id: str) -> None:
        with self._lock:
            self._paused_runs.discard(run_id)
            self._pause_before_nodes.pop(run_id, None)

    def request_cancel(self, run_id: str, *, before_node_id: str | None = None) -> None:
        with self._lock:
            if before_node_id is None:
                self._cancelled_runs.add(run_id)
            else:
                self._cancel_before_nodes.setdefault(run_id, set()).add(before_node_id)

    def clear_cancel(self, run_id: str) -> None:
        with self._lock:
            self._cancelled_runs.discard(run_id)
            self._cancel_before_nodes.pop(run_id, None)

    def should_pause(self, run_id: str, node_id: str | None = None) -> bool:
        with self._lock:
            if run_id in self._paused_runs:
                return True
            return node_id is not None and node_id in self._pause_before_nodes.get(run_id, set())

    def should_cancel(self, run_id: str, node_id: str | None = None) -> bool:
        with self._lock:
            if run_id in self._cancelled_runs:
                return True
            return node_id is not None and node_id in self._cancel_before_nodes.get(run_id, set())


class SQLiteWorkflowControlState:
    """Cross-process workflow control flags backed by SQLite."""

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
                CREATE TABLE IF NOT EXISTS runtime_control (
                    run_id TEXT PRIMARY KEY,
                    pause_all INTEGER NOT NULL DEFAULT 0,
                    cancel_all INTEGER NOT NULL DEFAULT 0,
                    pause_nodes_json TEXT NOT NULL DEFAULT '[]',
                    cancel_nodes_json TEXT NOT NULL DEFAULT '[]'
                )
                """
            )

    def request_pause(self, run_id: str, *, before_node_id: str | None = None) -> None:
        self._update(run_id, "pause", before_node_id, enabled=True)

    def clear_pause(self, run_id: str) -> None:
        self._clear(run_id, "pause")

    def request_cancel(self, run_id: str, *, before_node_id: str | None = None) -> None:
        self._update(run_id, "cancel", before_node_id, enabled=True)

    def clear_cancel(self, run_id: str) -> None:
        self._clear(run_id, "cancel")

    def should_pause(self, run_id: str, node_id: str | None = None) -> bool:
        return self._should(run_id, "pause", node_id)

    def should_cancel(self, run_id: str, node_id: str | None = None) -> bool:
        return self._should(run_id, "cancel", node_id)

    def _row(self, conn: sqlite3.Connection, run_id: str) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM runtime_control WHERE run_id = ?",
            (run_id,),
        ).fetchone()

    def _ensure(self, conn: sqlite3.Connection, run_id: str) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO runtime_control (run_id) VALUES (?)",
            (run_id,),
        )

    def _update(
        self,
        run_id: str,
        kind: str,
        node_id: str | None,
        *,
        enabled: bool,
    ) -> None:
        all_column = f"{kind}_all"
        nodes_column = f"{kind}_nodes_json"
        with self._lock, self._connect() as conn:
            self._ensure(conn, run_id)
            if node_id is None:
                conn.execute(
                    f"UPDATE runtime_control SET {all_column} = ? WHERE run_id = ?",
                    (1 if enabled else 0, run_id),
                )
                return
            row = self._row(conn, run_id)
            nodes = set(json.loads(row[nodes_column])) if row is not None else set()
            if enabled:
                nodes.add(node_id)
            else:
                nodes.discard(node_id)
            conn.execute(
                f"UPDATE runtime_control SET {nodes_column} = ? WHERE run_id = ?",
                (json.dumps(sorted(nodes)), run_id),
            )

    def _clear(self, run_id: str, kind: str) -> None:
        with self._lock, self._connect() as conn:
            self._ensure(conn, run_id)
            conn.execute(
                f"UPDATE runtime_control SET {kind}_all = 0, "
                f"{kind}_nodes_json = '[]' WHERE run_id = ?",
                (run_id,),
            )

    def _should(self, run_id: str, kind: str, node_id: str | None) -> bool:
        with self._lock, self._connect() as conn:
            row = self._row(conn, run_id)
        if row is None:
            return False
        if bool(row[f"{kind}_all"]):
            return True
        nodes = set(json.loads(row[f"{kind}_nodes_json"]))
        return node_id is not None and node_id in nodes
