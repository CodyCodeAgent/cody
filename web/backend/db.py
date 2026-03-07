"""SQLite database for web backend project management."""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class Project:
    id: str
    name: str
    description: str
    workdir: str
    code_paths: list[str] = field(default_factory=list)
    session_id: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Task:
    id: str
    project_id: str
    name: str
    branch_name: str
    session_id: Optional[str] = None
    status: str = "active"  # active, completed, archived
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
                    code_paths TEXT DEFAULT '[]',
                    session_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    branch_name TEXT NOT NULL,
                    session_id TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
            """)
            # Migration: add code_paths column if missing
            cursor = conn.execute("PRAGMA table_info(projects)")
            columns = {row["name"] for row in cursor.fetchall()}
            if "code_paths" not in columns:
                conn.execute("ALTER TABLE projects ADD COLUMN code_paths TEXT DEFAULT '[]'")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _gen_id() -> str:
        return uuid.uuid4().hex[:12]

    def _row_to_project(self, row: sqlite3.Row) -> Project:
        code_paths_raw = row["code_paths"] if "code_paths" in row.keys() else "[]"
        try:
            code_paths = json.loads(code_paths_raw) if code_paths_raw else []
        except (json.JSONDecodeError, TypeError):
            code_paths = []
        return Project(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            workdir=row["workdir"],
            code_paths=code_paths,
            session_id=row["session_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"],
            branch_name=row["branch_name"],
            session_id=row["session_id"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_project(
        self,
        name: str,
        description: str = "",
        workdir: str = "",
        code_paths: Optional[list[str]] = None,
    ) -> Project:
        """Create a new project."""
        now = self._now()
        paths = code_paths or []
        project = Project(
            id=self._gen_id(),
            name=name,
            description=description,
            workdir=workdir,
            code_paths=paths,
            created_at=now,
            updated_at=now,
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO projects (id, name, description, workdir, code_paths, "
                "session_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (project.id, project.name, project.description,
                 project.workdir, json.dumps(paths),
                 project.session_id,
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
        code_paths: Optional[list[str]] = None,
    ) -> Optional[Project]:
        """Update project fields. Returns None if not found."""
        project = self.get_project(project_id)
        if project is None:
            return None

        new_name = name if name is not None else project.name
        new_desc = description if description is not None else project.description
        new_paths = code_paths if code_paths is not None else project.code_paths
        now = self._now()

        with self._connect() as conn:
            conn.execute(
                "UPDATE projects SET name = ?, description = ?, code_paths = ?, "
                "updated_at = ? WHERE id = ?",
                (new_name, new_desc, json.dumps(new_paths), now, project_id),
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

    # ── Task CRUD ────────────────────────────────────────────────────────────

    def create_task(
        self,
        project_id: str,
        name: str,
        branch_name: str,
    ) -> Task:
        """Create a new development task under a project."""
        now = self._now()
        task = Task(
            id=self._gen_id(),
            project_id=project_id,
            name=name,
            branch_name=branch_name,
            created_at=now,
            updated_at=now,
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO tasks (id, project_id, name, branch_name, session_id, "
                "status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (task.id, task.project_id, task.name, task.branch_name,
                 task.session_id, task.status, task.created_at, task.updated_at),
            )
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_task(row)

    def list_tasks(self, project_id: str) -> list[Task]:
        """List all tasks for a project, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE project_id = ? ORDER BY updated_at DESC",
                (project_id,),
            ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def update_task(
        self,
        task_id: str,
        name: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[Task]:
        """Update a task. Returns None if not found."""
        task = self.get_task(task_id)
        if task is None:
            return None

        new_name = name if name is not None else task.name
        new_status = status if status is not None else task.status
        now = self._now()

        with self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET name = ?, status = ?, updated_at = ? WHERE id = ?",
                (new_name, new_status, now, task_id),
            )
        return self.get_task(task_id)

    def delete_task(self, task_id: str) -> bool:
        """Delete a task. Returns True if deleted."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM tasks WHERE id = ?", (task_id,)
            )
        return cursor.rowcount > 0

    def set_task_session_id(self, task_id: str, session_id: str) -> None:
        """Link a cody session to a task."""
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET session_id = ?, updated_at = ? WHERE id = ?",
                (session_id, now, task_id),
            )
