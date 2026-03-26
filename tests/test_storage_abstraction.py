"""Tests for storage layer abstraction (#12)."""

from unittest.mock import MagicMock, patch

from cody.core.storage import (
    SessionStoreProtocol,
    AuditLoggerProtocol,
    FileHistoryProtocol,
)
from cody.core.session import SessionStore
from cody.core.audit import AuditLogger
from cody.core.file_history import FileHistory
from cody.core.config import Config
from cody.core.runner import AgentRunner


# ── Protocol conformance ────────────────────────────────────────────────────


class TestProtocolConformance:
    """Default SQLite implementations satisfy the Protocols."""

    def test_session_store_satisfies_protocol(self, tmp_path):
        store = SessionStore(db_path=tmp_path / "test.db")
        assert isinstance(store, SessionStoreProtocol)
        store.close()

    def test_audit_logger_satisfies_protocol(self, tmp_path):
        logger = AuditLogger(db_path=tmp_path / "audit.db")
        assert isinstance(logger, AuditLoggerProtocol)
        logger.close()

    def test_file_history_satisfies_protocol(self, tmp_path):
        history = FileHistory(workdir=tmp_path)
        assert isinstance(history, FileHistoryProtocol)

    def test_file_history_close(self, tmp_path):
        """FileHistory.close() works for both in-memory and persistent modes."""
        history = FileHistory(workdir=tmp_path)
        history.close()  # no-op for in-memory, should not raise

        history_persist = FileHistory(workdir=tmp_path, persist=True)
        history_persist.close()
        assert history_persist._db is None


class TestCustomImplementation:
    """Custom implementations satisfy the Protocols."""

    def test_custom_session_store(self):
        class MySessionStore:
            def close(self): pass
            def create_session(self, title="", model="", workdir=""): pass
            def add_message(self, session_id, role, content, images=None): pass
            def get_session(self, session_id): pass
            def list_sessions(self, limit=20): return []
            def delete_session(self, session_id): return False
            def get_latest_session(self, workdir=None): return None
            def get_message_count(self, session_id): return 0
            def update_title(self, session_id, title): pass
            def save_compaction(self, session_id, summary, up_to_message_id): pass
            def get_messages_after(self, session_id, after_id): return []
            def get_last_message_id(self, session_id): return None

        assert isinstance(MySessionStore(), SessionStoreProtocol)

    def test_custom_audit_logger(self):
        class MyAuditLogger:
            def close(self): pass
            def log(self, event, tool_name=None, args_summary=None,
                    result_summary=None, session_id=None, workdir=None,
                    success=True): pass
            def query(self, event=None, since=None, limit=50): return []
            def count(self, event=None): return 0
            def clear(self, before=None): return 0

        assert isinstance(MyAuditLogger(), AuditLoggerProtocol)

    def test_custom_file_history(self):
        class MyFileHistory:
            def record(self, file_path, old_content, new_content,
                       operation="write"): pass
            def undo(self): return None
            def redo(self): return None
            def list_changes(self, limit=20): return []
            def can_undo(self): return False
            def can_redo(self): return False

        assert isinstance(MyFileHistory(), FileHistoryProtocol)


# ── Runner injection ────────────────────────────────────────────────────────


class TestRunnerInjection:
    def test_runner_uses_injected_audit_logger(self, tmp_path):
        mock_logger = MagicMock()
        with patch.object(AgentRunner, "_create_agent", return_value=MagicMock()):
            runner = AgentRunner(
                config=Config(), workdir=tmp_path,
                audit_logger=mock_logger,
            )
        assert runner._audit_logger is mock_logger

    def test_runner_uses_injected_file_history(self, tmp_path):
        mock_history = MagicMock()
        with patch.object(AgentRunner, "_create_agent", return_value=MagicMock()):
            runner = AgentRunner(
                config=Config(), workdir=tmp_path,
                file_history=mock_history,
            )
        assert runner._file_history is mock_history

    def test_runner_creates_defaults_when_not_injected(self, tmp_path):
        with patch.object(AgentRunner, "_create_agent", return_value=MagicMock()):
            runner = AgentRunner(config=Config(), workdir=tmp_path)
        assert isinstance(runner._audit_logger, AuditLogger)
        assert isinstance(runner._file_history, FileHistory)

    def test_runner_passes_storage_to_sub_agent_manager(self, tmp_path):
        mock_logger = MagicMock()
        mock_history = MagicMock()
        with patch.object(AgentRunner, "_create_agent", return_value=MagicMock()):
            runner = AgentRunner(
                config=Config(), workdir=tmp_path,
                audit_logger=mock_logger,
                file_history=mock_history,
            )
        assert runner._sub_agent_manager._injected_audit_logger is mock_logger
        assert runner._sub_agent_manager._injected_file_history is mock_history


# ── SDK Builder injection ───────────────────────────────────────────────────


class TestBuilderInjection:
    def test_session_store_method(self):
        from cody.sdk.client import CodyBuilder
        mock_store = MagicMock()
        builder = CodyBuilder()
        result = builder.session_store(mock_store)
        assert result is builder
        assert builder._session_store is mock_store

    def test_audit_logger_method(self):
        from cody.sdk.client import CodyBuilder
        mock_logger = MagicMock()
        builder = CodyBuilder()
        result = builder.audit_logger(mock_logger)
        assert result is builder
        assert builder._audit_logger is mock_logger

    def test_file_history_method(self):
        from cody.sdk.client import CodyBuilder
        mock_history = MagicMock()
        builder = CodyBuilder()
        result = builder.file_history(mock_history)
        assert result is builder
        assert builder._file_history is mock_history

    def test_builder_passes_storage_to_client(self):
        from cody.sdk.client import Cody, AsyncCodyClient
        mock_store = MagicMock()
        mock_logger = MagicMock()
        mock_history = MagicMock()

        with patch.object(AsyncCodyClient, "__init__", return_value=None) as mock_init:
            (Cody()
                .session_store(mock_store)
                .audit_logger(mock_logger)
                .file_history(mock_history)
                .build())
            _, kwargs = mock_init.call_args
            assert kwargs["session_store"] is mock_store
            assert kwargs["audit_logger"] is mock_logger
            assert kwargs["file_history"] is mock_history

    def test_builder_passes_none_when_not_set(self):
        from cody.sdk.client import Cody, AsyncCodyClient

        with patch.object(AsyncCodyClient, "__init__", return_value=None) as mock_init:
            Cody().build()
            _, kwargs = mock_init.call_args
            assert kwargs["session_store"] is None
            assert kwargs["audit_logger"] is None
            assert kwargs["file_history"] is None


# ── Client uses injected session store ──────────────────────────────────────


class TestClientSessionStore:
    def test_client_uses_injected_session_store(self):
        from cody.sdk.client import AsyncCodyClient
        mock_store = MagicMock()
        client = AsyncCodyClient(
            workdir=".", session_store=mock_store,
        )
        assert client.get_session_store() is mock_store

    def test_client_creates_default_session_store(self, tmp_path):
        from cody.sdk.client import AsyncCodyClient
        client = AsyncCodyClient(workdir=str(tmp_path))
        store = client.get_session_store()
        assert isinstance(store, SessionStore)
        store.close()
