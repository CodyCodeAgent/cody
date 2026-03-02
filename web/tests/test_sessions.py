"""Tests for /sessions endpoints — migrated from test_server.py."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from cody.core.session import SessionStore
from web.backend.app import app


def test_create_session(tmp_path):
    """POST /sessions creates a new session."""
    store = SessionStore(db_path=tmp_path / "test.db")

    with patch("web.backend.routes.sessions.get_session_store", return_value=store):
        client = TestClient(app)
        resp = client.post("/sessions?title=my+chat&model=test-model")

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "my chat"
    assert data["model"] == "test-model"
    assert data["message_count"] == 0
    assert len(data["id"]) == 12


def test_list_sessions(tmp_path):
    """GET /sessions lists recent sessions."""
    store = SessionStore(db_path=tmp_path / "test.db")
    store.create_session(title="session 1")
    store.create_session(title="session 2")

    with patch("web.backend.routes.sessions.get_session_store", return_value=store):
        client = TestClient(app)
        resp = client.get("/sessions")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["sessions"]) == 2


def test_list_sessions_empty(tmp_path):
    """GET /sessions returns empty list when no sessions."""
    store = SessionStore(db_path=tmp_path / "test.db")

    with patch("web.backend.routes.sessions.get_session_store", return_value=store):
        client = TestClient(app)
        resp = client.get("/sessions")

    assert resp.status_code == 200
    assert resp.json()["sessions"] == []


def test_get_session_detail(tmp_path):
    """GET /sessions/:id returns session with messages."""
    store = SessionStore(db_path=tmp_path / "test.db")
    session = store.create_session(title="test chat")
    store.add_message(session.id, "user", "hello")
    store.add_message(session.id, "assistant", "hi there")

    with patch("web.backend.routes.sessions.get_session_store", return_value=store):
        client = TestClient(app)
        resp = client.get(f"/sessions/{session.id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == session.id
    assert data["title"] == "test chat"
    assert data["message_count"] == 2
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "hello"
    assert data["messages"][1]["role"] == "assistant"


def test_get_session_not_found(tmp_path):
    """GET /sessions/:id returns 404 for nonexistent session."""
    store = SessionStore(db_path=tmp_path / "test.db")

    with patch("web.backend.routes.sessions.get_session_store", return_value=store):
        client = TestClient(app)
        resp = client.get("/sessions/nonexistent_id")

    assert resp.status_code == 404


def test_delete_session(tmp_path):
    """DELETE /sessions/:id deletes session."""
    store = SessionStore(db_path=tmp_path / "test.db")
    session = store.create_session(title="to delete")

    with patch("web.backend.routes.sessions.get_session_store", return_value=store):
        client = TestClient(app)
        resp = client.delete(f"/sessions/{session.id}")

    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"
    assert store.get_session(session.id) is None


def test_delete_session_not_found(tmp_path):
    """DELETE /sessions/:id returns 404 for nonexistent session."""
    store = SessionStore(db_path=tmp_path / "test.db")

    with patch("web.backend.routes.sessions.get_session_store", return_value=store):
        client = TestClient(app)
        resp = client.delete("/sessions/nonexistent_id")

    assert resp.status_code == 404
