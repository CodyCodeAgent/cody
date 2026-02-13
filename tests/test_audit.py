"""Tests for audit logging"""

import time
from datetime import datetime, timezone, timedelta


from cody.core.audit import AuditEvent, AuditLogger, _truncate


# ── _truncate ────────────────────────────────────────────────────────────────


def test_truncate_short_string():
    assert _truncate("hello", 10) == "hello"


def test_truncate_exact_length():
    assert _truncate("hello", 5) == "hello"


def test_truncate_long_string():
    result = _truncate("hello world", 8)
    assert result == "hello..."
    assert len(result) == 8


# ── AuditLogger basic ───────────────────────────────────────────────────────


def test_log_basic(tmp_path):
    db = tmp_path / "audit.db"
    logger = AuditLogger(db_path=db)

    entry = logger.log(event=AuditEvent.TOOL_CALL, tool_name="read_file")
    assert entry.event == "tool_call"
    assert entry.tool_name == "read_file"
    assert entry.success is True
    assert len(entry.id) == 12


def test_log_with_all_fields(tmp_path):
    db = tmp_path / "audit.db"
    logger = AuditLogger(db_path=db)

    entry = logger.log(
        event=AuditEvent.FILE_WRITE,
        tool_name="write_file",
        args_summary="path=hello.py",
        result_summary="Written 100 bytes",
        session_id="abc123",
        workdir="/tmp/project",
        success=True,
    )
    assert entry.event == "file_write"
    assert entry.args_summary == "path=hello.py"
    assert entry.result_summary == "Written 100 bytes"
    assert entry.session_id == "abc123"
    assert entry.workdir == "/tmp/project"


def test_log_failure(tmp_path):
    db = tmp_path / "audit.db"
    logger = AuditLogger(db_path=db)

    entry = logger.log(
        event=AuditEvent.COMMAND_EXEC,
        tool_name="exec_command",
        success=False,
    )
    assert entry.success is False


def test_log_truncates_long_args(tmp_path):
    db = tmp_path / "audit.db"
    logger = AuditLogger(db_path=db)

    long_args = "x" * 1000
    entry = logger.log(event=AuditEvent.TOOL_CALL, args_summary=long_args)
    assert len(entry.args_summary) == 500
    assert entry.args_summary.endswith("...")


# ── query ────────────────────────────────────────────────────────────────────


def test_query_all(tmp_path):
    db = tmp_path / "audit.db"
    logger = AuditLogger(db_path=db)

    logger.log(event=AuditEvent.TOOL_CALL, tool_name="read_file")
    logger.log(event=AuditEvent.FILE_WRITE, tool_name="write_file")
    logger.log(event=AuditEvent.COMMAND_EXEC, tool_name="exec_command")

    entries = logger.query()
    assert len(entries) == 3
    # Most recent first
    assert entries[0].tool_name == "exec_command"


def test_query_by_event(tmp_path):
    db = tmp_path / "audit.db"
    logger = AuditLogger(db_path=db)

    logger.log(event=AuditEvent.TOOL_CALL, tool_name="read_file")
    logger.log(event=AuditEvent.FILE_WRITE, tool_name="write_file")
    logger.log(event=AuditEvent.TOOL_CALL, tool_name="grep")

    entries = logger.query(event=AuditEvent.TOOL_CALL)
    assert len(entries) == 2


def test_query_with_limit(tmp_path):
    db = tmp_path / "audit.db"
    logger = AuditLogger(db_path=db)

    for i in range(10):
        logger.log(event=AuditEvent.TOOL_CALL, tool_name=f"tool_{i}")

    entries = logger.query(limit=3)
    assert len(entries) == 3


def test_query_since(tmp_path):
    db = tmp_path / "audit.db"
    logger = AuditLogger(db_path=db)

    logger.log(event=AuditEvent.TOOL_CALL, tool_name="old")
    # Use a future timestamp for the "since" filter
    future = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
    time.sleep(0.01)

    # These entries should appear after our query time
    entries_before = logger.query(since=future)
    assert len(entries_before) == 0


def test_query_empty(tmp_path):
    db = tmp_path / "audit.db"
    logger = AuditLogger(db_path=db)
    entries = logger.query()
    assert entries == []


# ── count ────────────────────────────────────────────────────────────────────


def test_count_all(tmp_path):
    db = tmp_path / "audit.db"
    logger = AuditLogger(db_path=db)

    logger.log(event=AuditEvent.TOOL_CALL)
    logger.log(event=AuditEvent.FILE_WRITE)
    logger.log(event=AuditEvent.TOOL_CALL)

    assert logger.count() == 3


def test_count_by_event(tmp_path):
    db = tmp_path / "audit.db"
    logger = AuditLogger(db_path=db)

    logger.log(event=AuditEvent.TOOL_CALL)
    logger.log(event=AuditEvent.FILE_WRITE)
    logger.log(event=AuditEvent.TOOL_CALL)

    assert logger.count(event=AuditEvent.TOOL_CALL) == 2
    assert logger.count(event=AuditEvent.FILE_WRITE) == 1


def test_count_empty(tmp_path):
    db = tmp_path / "audit.db"
    logger = AuditLogger(db_path=db)
    assert logger.count() == 0


# ── clear ────────────────────────────────────────────────────────────────────


def test_clear_all(tmp_path):
    db = tmp_path / "audit.db"
    logger = AuditLogger(db_path=db)

    logger.log(event=AuditEvent.TOOL_CALL)
    logger.log(event=AuditEvent.FILE_WRITE)

    deleted = logger.clear()
    assert deleted == 2
    assert logger.count() == 0


def test_clear_before(tmp_path):
    db = tmp_path / "audit.db"
    logger = AuditLogger(db_path=db)

    logger.log(event=AuditEvent.TOOL_CALL)
    cutoff = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()

    deleted = logger.clear(before=cutoff)
    assert deleted == 1
    assert logger.count() == 0


# ── persistence ──────────────────────────────────────────────────────────────


def test_persistence_across_instances(tmp_path):
    db = tmp_path / "audit.db"

    logger1 = AuditLogger(db_path=db)
    logger1.log(event=AuditEvent.TOOL_CALL, tool_name="read_file")

    logger2 = AuditLogger(db_path=db)
    entries = logger2.query()
    assert len(entries) == 1
    assert entries[0].tool_name == "read_file"


# ── AuditEvent constants ────────────────────────────────────────────────────


def test_audit_event_values():
    assert AuditEvent.TOOL_CALL == "tool_call"
    assert AuditEvent.FILE_WRITE == "file_write"
    assert AuditEvent.FILE_EDIT == "file_edit"
    assert AuditEvent.COMMAND_EXEC == "command_exec"
    assert AuditEvent.API_REQUEST == "api_request"
    assert AuditEvent.AUTH_LOGIN == "auth_login"
    assert AuditEvent.AUTH_FAILURE == "auth_failure"
    assert AuditEvent.PERMISSION_DENIED == "permission_denied"
