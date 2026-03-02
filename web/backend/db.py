"""SQLite database for web backend project management."""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class Project:
    id: str
    name: str
    description: str
    workdir: str
    session_id: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


class ProjectStore:
    """SQLite-backed project store for the web backend."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            default_dir = Path.home() / ".cody"
            default_dir.mkdir(parents=True, exist_ok=True)
            db_path = default_dir / "web.db"
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    workdir TEXT NOT NULL,
                    session_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _gen_id() -> str:
        return uuid.uuid4().hex[:12]

    def _row_to_project(self, row: sqlite3.Row) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            workdir=row["workdir"],
            session_id=row["session_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_project(
        self,
        name: str,
        description: str = "",
        workdir: str = "",
    ) -> Project:
        """Create a new project."""
        now = self._now()
        project = Project(
            id=self._gen_id(),
            name=name,
            description=description,
            workdir=workdir,
            created_at=now,
            updated_at=now,
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO projects (id, name, description, workdir, session_id, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (project.id, project.name, project.description,
                 project.workdir, project.session_id,
                 project.created_at, project.updated_at),
            )
        return project

    def get_project(self, project_id: str) -> Optional[Project]:
        """Get a project by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_project(row)

    def list_projects(self) -> list[Project]:
        """List all projects, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY updated_at DESC"
            ).fetchall()
        return [self._row_to_project(r) for r in rows]

    def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Project]:
        """Update project name and/or description. Returns None if not found."""
        project = self.get_project(project_id)
        if project is None:
            return None

        new_name = name if name is not None else project.name
        new_desc = description if description is not None else project.description
        now = self._now()

        with self._connect() as conn:
            conn.execute(
                "UPDATE projects SET name = ?, description = ?, updated_at = ? "
                "WHERE id = ?",
                (new_name, new_desc, now, project_id),
            )
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> bool:
        """Delete a project. Returns True if deleted, False if not found."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM projects WHERE id = ?", (project_id,)
            )
        return cursor.rowcount > 0

    def set_session_id(self, project_id: str, session_id: str) -> None:
        """Link a cody session to a project."""
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE projects SET session_id = ?, updated_at = ? WHERE id = ?",
                (session_id, now, project_id),
            )
