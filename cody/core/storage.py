"""Abstract storage protocols for dependency injection (#12).

Defines Protocol classes for SessionStore, AuditLogger, and FileHistory.
The default SQLite implementations in session.py, audit.py, and file_history.py
satisfy these protocols via structural subtyping — no inheritance required.

SDK consumers can provide their own implementations (e.g. PostgreSQL, DynamoDB)
by passing objects that conform to these protocols.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .audit import AuditEntry
    from .file_history import FileChange
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
