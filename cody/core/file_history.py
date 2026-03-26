"""File modification history for undo/redo support"""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class FileChange:
    """A single file modification record."""
    id: str
    file_path: str
    old_content: str
    new_content: str
    operation: str  # "write", "edit", "patch"
    timestamp: str


class FileHistory:
    """Tracks file modifications for undo/redo.

    Maintains a per-workdir stack of file changes.
    When persist=True, changes are also stored in SQLite for cross-session recovery.
    """

    def __init__(self, workdir: Path, max_history: int = 100, persist: bool = False):
        self._workdir = workdir.resolve()
        self._max_history = max_history
        self._persist = persist
        self._undo_stack: list[FileChange] = []
        self._redo_stack: list[FileChange] = []
        self._db: Optional[sqlite3.Connection] = None

        if persist:
            self._db_path = self._workdir / ".cody" / "file_history.db"
            self._init_db()
            self._load_history()

    @property
    def workdir(self) -> Path:
        return self._workdir

    def _init_db(self) -> None:
        """Initialize SQLite database for persistent history."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self._db_path))
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS file_changes ("
            "  id TEXT PRIMARY KEY,"
            "  file_path TEXT NOT NULL,"
            "  old_content TEXT NOT NULL,"
            "  new_content TEXT NOT NULL,"
            "  operation TEXT NOT NULL,"
            "  timestamp TEXT NOT NULL"
            ")"
        )
        self._db.commit()

    def _load_history(self) -> None:
        """Load history from SQLite on startup."""
        if not self._db:
            return
        cursor = self._db.execute(
            "SELECT id, file_path, old_content, new_content, operation, timestamp "
            "FROM file_changes ORDER BY timestamp ASC LIMIT ?",
            (self._max_history,),
        )
        for row in cursor:
            self._undo_stack.append(FileChange(
                id=row[0], file_path=row[1], old_content=row[2],
                new_content=row[3], operation=row[4], timestamp=row[5],
            ))

    def _save_change(self, change: FileChange) -> None:
        """Persist a change to SQLite."""
        if not self._db:
            return
        self._db.execute(
            "INSERT OR REPLACE INTO file_changes "
            "(id, file_path, old_content, new_content, operation, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (change.id, change.file_path, change.old_content,
             change.new_content, change.operation, change.timestamp),
        )
        # Enforce max history in DB
        self._db.execute(
            "DELETE FROM file_changes WHERE id NOT IN ("
            "  SELECT id FROM file_changes ORDER BY timestamp DESC LIMIT ?"
            ")",
            (self._max_history,),
        )
        self._db.commit()

    def record(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
        operation: str = "write",
    ) -> FileChange:
        """Record a file modification. Clears the redo stack."""
        change = FileChange(
            id=uuid.uuid4().hex[:12],
            file_path=file_path,
            old_content=old_content,
            new_content=new_content,
            operation=operation,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._undo_stack.append(change)
        self._redo_stack.clear()

        # Enforce max history
        if len(self._undo_stack) > self._max_history:
            self._undo_stack = self._undo_stack[-self._max_history:]

        if self._persist:
            self._save_change(change)

        return change

    def undo(self) -> Optional[FileChange]:
        """Undo the last file modification.

        Restores the file to its previous content and moves the change to redo stack.
        Returns the undone change, or None if nothing to undo.
        """
        if not self._undo_stack:
            return None

        change = self._undo_stack.pop()
        file_path = Path(change.file_path)
        full_path = file_path if file_path.is_absolute() else self._workdir / file_path

        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(change.old_content, encoding="utf-8")

        self._redo_stack.append(change)
        return change

    def redo(self) -> Optional[FileChange]:
        """Redo a previously undone modification.

        Re-applies the change and moves it back to the undo stack.
        Returns the redone change, or None if nothing to redo.
        """
        if not self._redo_stack:
            return None

        change = self._redo_stack.pop()
        file_path = Path(change.file_path)
        full_path = file_path if file_path.is_absolute() else self._workdir / file_path

        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(change.new_content, encoding="utf-8")

        self._undo_stack.append(change)
        return change

    def list_changes(self, limit: int = 20) -> list[FileChange]:
        """List recent undoable changes (most recent first)."""
        return list(reversed(self._undo_stack[-limit:]))

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def close(self) -> None:
        """Close the underlying database connection (if any)."""
        if self._db:
            self._db.close()
            self._db = None

    @property
    def undo_count(self) -> int:
        return len(self._undo_stack)

    @property
    def redo_count(self) -> int:
        return len(self._redo_stack)
