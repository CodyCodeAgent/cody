"""Tests for stateless mode and Null storage implementations."""

import pytest
from unittest.mock import MagicMock, patch

from cody.core.storage import (
    SessionStoreProtocol,
    AuditLoggerProtocol,
    FileHistoryProtocol,
    MemoryStoreProtocol,
    NullSessionStore,
    NullAuditLogger,
    NullFileHistory,
    NullMemoryStore,
)


# ── Null implementations satisfy Protocols ──────────────────────────────────


class TestNullProtocolConformance:
    def test_null_session_store_satisfies_protocol(self):
        assert isinstance(NullSessionStore(), SessionStoreProtocol)

    def test_null_audit_logger_satisfies_protocol(self):
        assert isinstance(NullAuditLogger(), AuditLoggerProtocol)

    def test_null_file_history_satisfies_protocol(self):
        assert isinstance(NullFileHistory(), FileHistoryProtocol)

    def test_null_memory_store_satisfies_protocol(self):
        assert isinstance(NullMemoryStore(), MemoryStoreProtocol)


# ── NullSessionStore behavior ───────────────────────────────────────────────


class TestNullSessionStore:
    def test_create_session_returns_session(self):
        store = NullSessionStore()
        session = store.create_session(title="test")
        assert session.title == "test"
        assert session.id  # has an id

    def test_add_message_returns_message(self):
        store = NullSessionStore()
        msg = store.add_message("sid", "user", "hello")
        assert msg.role == "user"
        assert msg.content == "hello"

    def test_get_session_returns_none(self):
        store = NullSessionStore()
        assert store.get_session("any") is None

    def test_list_sessions_returns_empty(self):
        store = NullSessionStore()
        assert store.list_sessions() == []

    def test_close_is_noop(self):
        NullSessionStore().close()  # should not raise


# ── NullAuditLogger behavior ───────────────────────────────────────────────


class TestNullAuditLogger:
    def test_log_returns_entry(self):
        logger = NullAuditLogger()
        entry = logger.log("tool_call", tool_name="grep")
        assert entry.event == "tool_call"
        assert entry.tool_name == "grep"

    def test_query_returns_empty(self):
        assert NullAuditLogger().query() == []

    def test_count_returns_zero(self):
        assert NullAuditLogger().count() == 0

    def test_clear_returns_zero(self):
        assert NullAuditLogger().clear() == 0


# ── NullFileHistory behavior ───────────────────────────────────────────────


class TestNullFileHistory:
    def test_record_returns_change(self):
        fh = NullFileHistory()
        change = fh.record("a.py", "old", "new")
        assert change.file_path == "a.py"

    def test_undo_returns_none(self):
        assert NullFileHistory().undo() is None

    def test_redo_returns_none(self):
        assert NullFileHistory().redo() is None

    def test_can_undo_is_false(self):
        assert NullFileHistory().can_undo() is False

    def test_can_redo_is_false(self):
        assert NullFileHistory().can_redo() is False


# ── NullMemoryStore behavior ───────────────────────────────────────────────


class TestNullMemoryStore:
    @pytest.mark.asyncio
    async def test_add_entries_is_noop(self):
        store = NullMemoryStore()
        await store.add_entries("conventions", [])  # should not raise

    def test_get_all_entries_returns_empty(self):
        assert NullMemoryStore().get_all_entries() == {}

    def test_get_memory_for_prompt_returns_empty(self):
        assert NullMemoryStore().get_memory_for_prompt() == ""

    def test_count_returns_empty(self):
        assert NullMemoryStore().count() == {}

    def test_clear_is_noop(self):
        NullMemoryStore().clear()  # should not raise


# ── MemoryStoreProtocol conformance for real implementation ────────────────


class TestMemoryStoreProtocolConformance:
    def test_project_memory_store_satisfies_protocol(self, tmp_path):
        from cody.core.memory import ProjectMemoryStore
        store = ProjectMemoryStore.from_workdir(tmp_path)
        assert isinstance(store, MemoryStoreProtocol)


# ── Builder .stateless() ───────────────────────────────────────────────────


class TestBuilderStateless:
    def test_stateless_method(self):
        from cody.sdk.client import CodyBuilder
        builder = CodyBuilder()
        result = builder.stateless()
        assert result is builder
        assert builder._stateless is True

    def test_memory_store_method(self):
        from cody.sdk.client import CodyBuilder
        mock_store = MagicMock()
        builder = CodyBuilder()
        result = builder.memory_store(mock_store)
        assert result is builder
        assert builder._memory_store is mock_store

    def test_stateless_injects_null_stores(self):
        from cody.sdk.client import Cody, AsyncCodyClient
        with patch.object(AsyncCodyClient, "__init__", return_value=None) as mock_init:
            Cody().stateless().build()
            _, kwargs = mock_init.call_args
            assert isinstance(kwargs["session_store"], NullSessionStore)
            assert isinstance(kwargs["audit_logger"], NullAuditLogger)
            assert isinstance(kwargs["file_history"], NullFileHistory)
            assert isinstance(kwargs["memory_store"], NullMemoryStore)

    def test_stateless_respects_explicit_overrides(self):
        from cody.sdk.client import Cody, AsyncCodyClient
        real_logger = MagicMock()
        with patch.object(AsyncCodyClient, "__init__", return_value=None) as mock_init:
            Cody().stateless().audit_logger(real_logger).build()
            _, kwargs = mock_init.call_args
            # audit_logger was explicitly set, should NOT be replaced
            assert kwargs["audit_logger"] is real_logger
            # Others should still be null
            assert isinstance(kwargs["session_store"], NullSessionStore)
            assert isinstance(kwargs["file_history"], NullFileHistory)
            assert isinstance(kwargs["memory_store"], NullMemoryStore)

    def test_non_stateless_passes_none(self):
        from cody.sdk.client import Cody, AsyncCodyClient, _BUILDER_UNSET
        with patch.object(AsyncCodyClient, "__init__", return_value=None) as mock_init:
            Cody().build()
            _, kwargs = mock_init.call_args
            assert kwargs["session_store"] is None
            assert kwargs["audit_logger"] is None
            assert kwargs["file_history"] is None
            assert kwargs["memory_store"] is _BUILDER_UNSET


# ── Runner memory_store injection ──────────────────────────────────────────


class TestRunnerMemoryStoreInjection:
    def test_runner_uses_injected_memory_store(self, tmp_path):
        from cody.core.runner import AgentRunner
        from cody.core.config import Config
        mock_store = MagicMock()
        with patch.object(AgentRunner, "_create_agent", return_value=MagicMock()):
            runner = AgentRunner(
                config=Config(), workdir=tmp_path,
                memory_store=mock_store,
            )
        assert runner._memory_store is mock_store

    def test_runner_uses_none_memory_store(self, tmp_path):
        from cody.core.runner import AgentRunner
        from cody.core.config import Config
        with patch.object(AgentRunner, "_create_agent", return_value=MagicMock()):
            runner = AgentRunner(
                config=Config(), workdir=tmp_path,
                memory_store=None,
            )
        assert runner._memory_store is None

    def test_runner_default_creates_memory_store(self, tmp_path):
        from cody.core.runner import AgentRunner
        from cody.core.config import Config
        from cody.core.memory import ProjectMemoryStore
        with patch.object(AgentRunner, "_create_agent", return_value=MagicMock()):
            runner = AgentRunner(config=Config(), workdir=tmp_path)
        assert isinstance(runner._memory_store, ProjectMemoryStore)


# ── SDK exports ────────────────────────────────────────────────────────────


class TestExports:
    def test_null_stores_importable_from_sdk(self):
        from cody.sdk import (
            NullSessionStore as NS,
            NullAuditLogger as NA,
            NullFileHistory as NF,
            NullMemoryStore as NM,
        )
        assert NS is NullSessionStore
        assert NA is NullAuditLogger
        assert NF is NullFileHistory
        assert NM is NullMemoryStore

    def test_protocols_importable_from_sdk(self):
        from cody.sdk import (
            SessionStoreProtocol,
            AuditLoggerProtocol,
            FileHistoryProtocol,
            MemoryStoreProtocol,
        )
        assert SessionStoreProtocol is not None
        assert AuditLoggerProtocol is not None
        assert FileHistoryProtocol is not None
        assert MemoryStoreProtocol is not None
