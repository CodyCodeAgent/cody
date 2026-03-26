"""Abstract storage protocols and null implementations for dependency injection.

Defines Protocol classes for SessionStore, AuditLogger, FileHistory, and
MemoryStore.  The default implementations (SQLite / JSON-file backed) satisfy
these protocols via structural subtyping — no inheritance required.

SDK consumers can provide their own implementations (e.g. PostgreSQL, DynamoDB)
by passing objects that conform to these protocols.

Null implementations (``NullSessionStore``, ``NullAuditLogger``,
``NullFileHistory``, ``NullMemoryStore``) are provided for stateless mode
where no persistence is desired.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .audit import AuditEntry
    from .file_history import FileChange
    from .memory import MemoryEntry
    from .prompt import ImageData
    from .session import Message, Session


@runtime_checkable
class SessionStoreProtocol(Protocol):
    """Protocol for session persistence."""

    def close(self) -> None: ...

    def create_session(
        self, title: str = "New session", model: str = "", workdir: str = ""
    ) -> Session: ...

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        images: Optional[list[ImageData]] = None,
    ) -> Message: ...

    def get_session(self, session_id: str) -> Optional[Session]: ...

    def list_sessions(self, limit: int = 20) -> list[Session]: ...

    def delete_session(self, session_id: str) -> bool: ...

    def get_latest_session(self, workdir: Optional[str] = None) -> Optional[Session]: ...

    def get_message_count(self, session_id: str) -> int: ...

    def update_title(self, session_id: str, title: str) -> None: ...

    def save_compaction(
        self, session_id: str, summary: str, up_to_message_id: int
    ) -> None: ...

    def get_messages_after(
        self, session_id: str, after_id: int
    ) -> list[Message]: ...

    def get_last_message_id(self, session_id: str) -> int | None: ...


@runtime_checkable
class AuditLoggerProtocol(Protocol):
    """Protocol for audit logging."""

    def close(self) -> None: ...

    def log(
        self,
        event: str,
        tool_name: Optional[str] = None,
        args_summary: Optional[str] = None,
        result_summary: Optional[str] = None,
        session_id: Optional[str] = None,
        workdir: Optional[str] = None,
        success: bool = True,
    ) -> AuditEntry: ...

    def query(
        self,
        event: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 50,
    ) -> list[AuditEntry]: ...

    def count(self, event: Optional[str] = None) -> int: ...

    def clear(self, before: Optional[str] = None) -> int: ...


@runtime_checkable
class FileHistoryProtocol(Protocol):
    """Protocol for file change tracking with undo/redo."""

    def record(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
        operation: str = "write",
    ) -> FileChange: ...

    def undo(self) -> Optional[FileChange]: ...

    def redo(self) -> Optional[FileChange]: ...

    def list_changes(self, limit: int = 20) -> list[FileChange]: ...

    def can_undo(self) -> bool: ...

    def can_redo(self) -> bool: ...

    def close(self) -> None: ...


@runtime_checkable
class MemoryStoreProtocol(Protocol):
    """Protocol for cross-session project memory."""

    async def add_entries(self, category: str, entries: list[MemoryEntry]) -> None: ...

    def get_all_entries(self) -> dict[str, list[MemoryEntry]]: ...

    def get_memory_for_prompt(self, max_tokens: int = 2000) -> str: ...

    async def cleanup(self) -> None: ...

    def count(self) -> dict[str, int]: ...

    def clear(self) -> None: ...


# ── Null implementations for stateless mode ─────────────────────────────────


class NullSessionStore:
    """No-op session store for stateless mode."""

    def close(self) -> None:
        pass

    def create_session(self, title="New session", model="", workdir=""):
        from .session import Session
        now = datetime.now(timezone.utc).isoformat()
        return Session(
            id=uuid.uuid4().hex[:12], title=title, messages=[],
            model=model, workdir=workdir,
            created_at=now, updated_at=now, message_count=0,
        )

    def add_message(self, session_id, role, content, images=None):
        from .session import Message
        return Message(role=role, content=content)

    def get_session(self, session_id):
        return None

    def list_sessions(self, limit=20):
        return []

    def delete_session(self, session_id):
        return False

    def get_latest_session(self, workdir=None):
        return None

    def get_message_count(self, session_id):
        return 0

    def update_title(self, session_id, title):
        pass

    def save_compaction(self, session_id, summary, up_to_message_id):
        pass

    def get_messages_after(self, session_id, after_id):
        return []

    def get_last_message_id(self, session_id):
        return None


class NullAuditLogger:
    """No-op audit logger for stateless mode."""

    def close(self) -> None:
        pass

    def log(self, event, tool_name=None, args_summary=None,
            result_summary=None, session_id=None, workdir=None, success=True):
        from .audit import AuditEntry
        return AuditEntry(
            id=0, timestamp=datetime.now(timezone.utc).isoformat(),
            event=event, tool_name=tool_name, args_summary=args_summary,
            result_summary=result_summary, session_id=session_id,
            workdir=workdir, success=success,
        )

    def query(self, event=None, since=None, limit=50):
        return []

    def count(self, event=None):
        return 0

    def clear(self, before=None):
        return 0


class NullFileHistory:
    """No-op file history for stateless mode."""

    def record(self, file_path, old_content, new_content, operation="write"):
        from .file_history import FileChange
        return FileChange(
            id=uuid.uuid4().hex[:12], file_path=file_path,
            old_content=old_content, new_content=new_content,
            operation=operation,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def undo(self):
        return None

    def redo(self):
        return None

    def list_changes(self, limit=20):
        return []

    def can_undo(self):
        return False

    def can_redo(self):
        return False

    def close(self) -> None:
        pass


class NullMemoryStore:
    """No-op memory store for stateless mode."""

    async def add_entries(self, category, entries):
        pass

    def get_all_entries(self):
        return {}

    def get_memory_for_prompt(self, max_tokens=2000):
        return ""

    async def cleanup(self):
        pass

    def count(self):
        return {}

    def clear(self):
        pass
