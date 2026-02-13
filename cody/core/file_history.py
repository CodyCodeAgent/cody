"""File modification history for undo/redo support"""

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
    """

    def __init__(self, workdir: Path, max_history: int = 100):
        self._workdir = workdir.resolve()
        self._max_history = max_history
        self._undo_stack: list[FileChange] = []
        self._redo_stack: list[FileChange] = []

    @property
    def workdir(self) -> Path:
        return self._workdir

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

        return change

    def undo(self) -> Optional[FileChange]:
        """Undo the last file modification.

        Restores the file to its previous content and moves the change to redo stack.
        Returns the undone change, or None if nothing to undo.
        """
        if not self._undo_stack:
            return None

        change = self._undo_stack.pop()
        full_path = self._workdir / change.file_path

        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(change.old_content)

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
        full_path = self._workdir / change.file_path

        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(change.new_content)

        self._undo_stack.append(change)
        return change

    def list_changes(self, limit: int = 20) -> list[FileChange]:
        """List recent undoable changes (most recent first)."""
        return list(reversed(self._undo_stack[-limit:]))

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    @property
    def undo_count(self) -> int:
        return len(self._undo_stack)

    @property
    def redo_count(self) -> int:
        return len(self._redo_stack)
