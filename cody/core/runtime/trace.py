"""Trace storage primitives for Cody's runtime."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
import json
import sqlite3

from .events import RunEvent


@dataclass
class InMemoryTraceStore:
    """Small append-only TraceStore implementation.

    This is intentionally simple and dependency-free. It gives the runtime a
    concrete event sink today while leaving room for SQLite/Postgres/object-store
    backed implementations later.
    """

    _events: list[RunEvent] = field(default_factory=list)
    _events_by_run: dict[str, list[RunEvent]] = field(default_factory=lambda: defaultdict(list))
    _lock: RLock = field(default_factory=RLock, repr=False)

    def append(self, event: RunEvent) -> RunEvent:
        """Append one event and return it for fluent producer code."""

        with self._lock:
            self._events.append(event)
            if event.run_id:
                self._events_by_run[event.run_id].append(event)
        return event

    def extend(self, events: list[RunEvent]) -> list[RunEvent]:
        """Append multiple events in order."""

        for event in events:
            self.append(event)
        return events

    def list_events(self, run_id: str | None = None) -> list[RunEvent]:
        """Return events in insertion order, optionally scoped to one run."""

        with self._lock:
            if run_id is None:
                return list(self._events)
            return list(self._events_by_run.get(run_id, []))

    def export_jsonl(self, run_id: str | None = None) -> str:
        """Export events as newline-delimited JSON-compatible strings."""

        return "\n".join(json.dumps(event.to_dict(), sort_keys=True) for event in self.list_events(run_id))


class SQLiteTraceStore:
    """SQLite-backed append-only TraceStore.

    This is the first durable TraceStore implementation. It intentionally stores
    the canonical event envelope as JSON while indexing the common timeline query
    fields needed by run inspection, replay, and future Web UI timelines.
    """

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
                CREATE TABLE IF NOT EXISTS runtime_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    run_id TEXT,
                    step_id TEXT,
                    parent_event_id TEXT,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    event_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runtime_events_run_seq "
                "ON runtime_events(run_id, seq)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runtime_events_type "
                "ON runtime_events(event_type)"
            )

    def append(self, event: RunEvent) -> RunEvent:
        """Persist one event and return it."""

        data = event.to_dict()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runtime_events (
                    event_id, run_id, step_id, parent_event_id, event_type,
                    timestamp, payload_json, event_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["event_id"],
                    data["run_id"],
                    data["step_id"],
                    data["parent_event_id"],
                    data["event_type"],
                    data["timestamp"],
                    json.dumps(data["payload"], sort_keys=True),
                    json.dumps(data, sort_keys=True),
                ),
            )
        return event

    def extend(self, events: list[RunEvent]) -> list[RunEvent]:
        for event in events:
            self.append(event)
        return events

    def list_events(self, run_id: str | None = None) -> list[RunEvent]:
        """Return events in persisted insertion order, optionally scoped to one run."""

        query = "SELECT event_json FROM runtime_events"
        params: tuple[str, ...] = ()
        if run_id is not None:
            query += " WHERE run_id = ?"
            params = (run_id,)
        query += " ORDER BY seq ASC"

        with self._lock, self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [RunEvent.from_dict(json.loads(row["event_json"])) for row in rows]

    def export_jsonl(self, run_id: str | None = None) -> str:
        return "\n".join(json.dumps(event.to_dict(), sort_keys=True) for event in self.list_events(run_id))
