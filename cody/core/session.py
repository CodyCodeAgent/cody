"""Session management with SQLite persistence"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .prompt import ImageData


@dataclass
class Message:
    """A single message in a conversation"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    images: list[ImageData] = field(default_factory=list)  # only for user messages


@dataclass
class Session:
    """A conversation session"""
    id: str
    title: str
    messages: list[Message]
    model: str
    workdir: str
    created_at: str
    updated_at: str


class SessionStore:
    """SQLite-backed session storage"""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path.home() / ".cody" / "sessions.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_db(self) -> None:
        """Create tables if they don't exist"""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    model TEXT NOT NULL DEFAULT '',
                    workdir TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id)
            """)
            # Migration: add images column for multimodal support
            try:
                conn.execute(
                    "ALTER TABLE messages ADD COLUMN images TEXT DEFAULT NULL"
                )
            except sqlite3.OperationalError:
                pass  # column already exists

    def create_session(
        self,
        title: str = "New session",
        model: str = "",
        workdir: str = "",
    ) -> Session:
        """Create a new session and return it"""
        now = datetime.now(timezone.utc).isoformat()
        session = Session(
            id=uuid.uuid4().hex[:12],
            title=title,
            messages=[],
            model=model,
            workdir=workdir,
            created_at=now,
            updated_at=now,
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, title, model, workdir, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session.id, session.title, session.model, session.workdir,
                 session.created_at, session.updated_at),
            )
        return session

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        images: Optional[list[ImageData]] = None,
    ) -> Message:
        """Add a message to a session"""
        image_list = list(images) if images else []
        images_json = json.dumps([img.to_dict() for img in image_list]) if image_list else None
        msg = Message(role=role, content=content, images=image_list)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content, timestamp, images) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, msg.role, msg.content, msg.timestamp, images_json),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
        return msg

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID (with messages)"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, title, model, workdir, created_at, updated_at "
                "FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return None

            msg_rows = conn.execute(
                "SELECT role, content, timestamp, images FROM messages "
                "WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()

            messages = []
            for r in msg_rows:
                imgs = []
                if r[3]:  # images JSON column
                    imgs = [ImageData.from_dict(d) for d in json.loads(r[3])]
                messages.append(Message(role=r[0], content=r[1], timestamp=r[2], images=imgs))

            return Session(
                id=row[0],
                title=row[1],
                messages=messages,
                model=row[2],
                workdir=row[3],
                created_at=row[4],
                updated_at=row[5],
            )

    def list_sessions(self, limit: int = 20) -> list[Session]:
        """List recent sessions (without messages for efficiency)"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, model, workdir, created_at, updated_at "
                "FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

            return [
                Session(
                    id=r[0],
                    title=r[1],
                    messages=[],
                    model=r[2],
                    workdir=r[3],
                    created_at=r[4],
                    updated_at=r[5],
                )
                for r in rows
            ]

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and its messages"""
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            cursor = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return cursor.rowcount > 0

    def get_latest_session(self, workdir: Optional[str] = None) -> Optional[Session]:
        """Get the most recently updated session, optionally filtered by workdir"""
        with self._connect() as conn:
            if workdir:
                row = conn.execute(
                    "SELECT id FROM sessions WHERE workdir = ? "
                    "ORDER BY updated_at DESC LIMIT 1",
                    (workdir,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id FROM sessions ORDER BY updated_at DESC LIMIT 1",
                ).fetchone()

            if not row:
                return None
            return self.get_session(row[0])

    def get_message_count(self, session_id: str) -> int:
        """Get the number of messages in a session"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return row[0] if row else 0

    def update_title(self, session_id: str, title: str) -> None:
        """Update session title"""
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET title = ? WHERE id = ?",
                (title, session_id),
            )
