"""Tests for /audit endpoint."""

from fastapi.testclient import TestClient

from cody.core.audit import AuditLogger
from web.backend.app import app
from web.backend.state import audit_logger_dep


def _client_with_logger(logger):
    """Create a TestClient with the given AuditLogger injected."""
    app.dependency_overrides[audit_logger_dep] = lambda: logger
    return TestClient(app)


def _cleanup():
    app.dependency_overrides.pop(audit_logger_dep, None)


def test_query_audit_empty(tmp_path):
    """GET /audit returns empty list when no entries."""
    logger = AuditLogger(db_path=tmp_path / "audit.db")
    client = _client_with_logger(logger)
    try:
        resp = client.get("/audit")
    finally:
        _cleanup()

    assert resp.status_code == 200
    data = resp.json()
    assert data["entries"] == []
    assert data["total"] == 0


def test_query_audit_with_entries(tmp_path):
    """GET /audit returns logged entries."""
    logger = AuditLogger(db_path=tmp_path / "audit.db")
    logger.log(event="tool_call", tool_name="read_file", args_summary="path=test.py")
    logger.log(event="command_exec", tool_name="exec_command", args_summary="cmd=ls")
    client = _client_with_logger(logger)
    try:
        resp = client.get("/audit")
    finally:
        _cleanup()

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entries"]) == 2
    assert data["total"] == 2
    # Entries should have expected fields
    entry = data["entries"][0]
    assert "id" in entry
    assert "timestamp" in entry
    assert "event" in entry
    assert "tool_name" in entry
    assert "success" in entry


def test_query_audit_filter_by_event(tmp_path):
    """GET /audit?event=tool_call filters by event type."""
    logger = AuditLogger(db_path=tmp_path / "audit.db")
    logger.log(event="tool_call", tool_name="read_file")
    logger.log(event="command_exec", tool_name="exec_command")
    logger.log(event="tool_call", tool_name="write_file")
    client = _client_with_logger(logger)
    try:
        resp = client.get("/audit", params={"event": "tool_call"})
    finally:
        _cleanup()

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entries"]) == 2
    assert data["total"] == 2
    assert all(e["event"] == "tool_call" for e in data["entries"])


def test_query_audit_limit(tmp_path):
    """GET /audit?limit=1 respects limit parameter."""
    logger = AuditLogger(db_path=tmp_path / "audit.db")
    for i in range(5):
        logger.log(event="tool_call", tool_name=f"tool_{i}")
    client = _client_with_logger(logger)
    try:
        resp = client.get("/audit", params={"limit": 2})
    finally:
        _cleanup()

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entries"]) == 2
    assert data["total"] == 5  # total count is unaffected by limit
