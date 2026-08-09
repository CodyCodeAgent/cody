"""Run and step registry stores for Cody runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
import json
import sqlite3

from .models import RunRecord, RunStatus, StepRecord


@dataclass
class InMemoryRunStore:
    """In-memory run/step registry for tests and local execution."""

    _runs: dict[str, RunRecord] = field(default_factory=dict)
    _steps: dict[str, StepRecord] = field(default_factory=dict)
    _steps_by_run: dict[str, list[str]] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock, repr=False)

    def save_run(self, run: RunRecord) -> RunRecord:
        with self._lock:
            self._runs[run.run_id] = run
        return run

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self, *, status: RunStatus | None = None) -> list[RunRecord]:
        with self._lock:
            runs = list(self._runs.values())
        if status is not None:
            return [run for run in runs if run.status == status]
        return runs

    def save_step(self, step: StepRecord) -> StepRecord:
        with self._lock:
            if step.step_id not in self._steps:
                self._steps_by_run.setdefault(step.run_id, []).append(step.step_id)
            self._steps[step.step_id] = step
        return step

    def get_step(self, step_id: str) -> StepRecord | None:
        with self._lock:
            return self._steps.get(step_id)

    def list_steps(self, run_id: str) -> list[StepRecord]:
        with self._lock:
            return [self._steps[step_id] for step_id in self._steps_by_run.get(run_id, [])]


class SQLiteRunStore:
    """SQLite-backed run/step registry for durable runtime status queries."""

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
                CREATE TABLE IF NOT EXISTS runtime_runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    workflow_id TEXT,
                    parent_run_id TEXT,
                    updated_at TEXT NOT NULL,
                    run_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runtime_runs_status_updated "
                "ON runtime_runs(status, updated_at)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_steps (
                    step_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    step_type TEXT NOT NULL,
                    node_id TEXT,
                    step_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runtime_steps_run "
                "ON runtime_steps(run_id)"
            )

    def save_run(self, run: RunRecord) -> RunRecord:
        data = run.to_dict()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runtime_runs (
                    run_id, status, workflow_id, parent_run_id, updated_at, run_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    data["run_id"],
                    data["status"],
                    data["workflow_id"],
                    data["parent_run_id"],
                    data["updated_at"],
                    json.dumps(data, sort_keys=True),
                ),
            )
        return run

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT run_json FROM runtime_runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return RunRecord.from_dict(json.loads(row["run_json"]))

    def list_runs(self, *, status: RunStatus | None = None) -> list[RunRecord]:
        query = "SELECT run_json FROM runtime_runs"
        params: tuple[str, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            params = (status.value,)
        query += " ORDER BY updated_at ASC"
        with self._lock, self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [RunRecord.from_dict(json.loads(row["run_json"])) for row in rows]

    def save_step(self, step: StepRecord) -> StepRecord:
        data = step.to_dict()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runtime_steps (
                    step_id, run_id, status, step_type, node_id, step_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    data["step_id"],
                    data["run_id"],
                    data["status"],
                    data["step_type"],
                    data["node_id"],
                    json.dumps(data, sort_keys=True),
                ),
            )
        return step

    def get_step(self, step_id: str) -> StepRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT step_json FROM runtime_steps WHERE step_id = ?", (step_id,)).fetchone()
        if row is None:
            return None
        return StepRecord.from_dict(json.loads(row["step_json"]))

    def list_steps(self, run_id: str) -> list[StepRecord]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT step_json FROM runtime_steps WHERE run_id = ? ORDER BY rowid ASC",
                (run_id,),
            ).fetchall()
        return [StepRecord.from_dict(json.loads(row["step_json"])) for row in rows]
