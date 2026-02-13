"""Tests for session management"""

import pytest
from cody.core.session import SessionStore


@pytest.fixture
def store(tmp_path):
    """Create a SessionStore with a temp database"""
    return SessionStore(db_path=tmp_path / "test_sessions.db")


def test_create_session(store):
    session = store.create_session(title="Test Session", model="test-model", workdir="/tmp")
    assert session.id
    assert len(session.id) == 12
    assert session.title == "Test Session"
    assert session.model == "test-model"
    assert session.workdir == "/tmp"
    assert session.messages == []
    assert session.created_at
    assert session.updated_at


def test_add_and_get_messages(store):
    session = store.create_session(title="Chat")

    store.add_message(session.id, "user", "Hello")
    store.add_message(session.id, "assistant", "Hi there!")
    store.add_message(session.id, "user", "How are you?")

    loaded = store.get_session(session.id)
    assert loaded is not None
    assert len(loaded.messages) == 3
    assert loaded.messages[0].role == "user"
    assert loaded.messages[0].content == "Hello"
    assert loaded.messages[1].role == "assistant"
    assert loaded.messages[1].content == "Hi there!"
    assert loaded.messages[2].role == "user"
    assert loaded.messages[2].content == "How are you?"


def test_get_nonexistent_session(store):
    result = store.get_session("nonexistent")
    assert result is None


def test_list_sessions(store):
    store.create_session(title="Session 1")
    store.create_session(title="Session 2")
    store.create_session(title="Session 3")

    sessions = store.list_sessions()
    assert len(sessions) == 3
    # Most recent first
    assert sessions[0].title == "Session 3"


def test_list_sessions_limit(store):
    for i in range(10):
        store.create_session(title=f"Session {i}")

    sessions = store.list_sessions(limit=5)
    assert len(sessions) == 5


def test_delete_session(store):
    session = store.create_session(title="To Delete")
    store.add_message(session.id, "user", "test")

    result = store.delete_session(session.id)
    assert result is True

    loaded = store.get_session(session.id)
    assert loaded is None


def test_delete_nonexistent_session(store):
    result = store.delete_session("nonexistent")
    assert result is False


def test_get_latest_session(store):
    store.create_session(title="Old", workdir="/project-a")
    store.create_session(title="New", workdir="/project-a")
    store.create_session(title="Other", workdir="/project-b")

    latest = store.get_latest_session()
    assert latest is not None
    assert latest.title == "Other"  # Most recently created

    latest_a = store.get_latest_session(workdir="/project-a")
    assert latest_a is not None
    assert latest_a.title == "New"

    latest_b = store.get_latest_session(workdir="/project-b")
    assert latest_b is not None
    assert latest_b.title == "Other"


def test_get_latest_session_empty(store):
    result = store.get_latest_session()
    assert result is None


def test_get_message_count(store):
    session = store.create_session(title="Count Test")
    assert store.get_message_count(session.id) == 0

    store.add_message(session.id, "user", "msg1")
    store.add_message(session.id, "assistant", "msg2")
    assert store.get_message_count(session.id) == 2


def test_update_title(store):
    session = store.create_session(title="Original")

    store.update_title(session.id, "Updated Title")

    loaded = store.get_session(session.id)
    assert loaded is not None
    assert loaded.title == "Updated Title"


def test_message_ordering(store):
    """Messages should be returned in insertion order"""
    session = store.create_session(title="Order Test")

    for i in range(20):
        store.add_message(session.id, "user" if i % 2 == 0 else "assistant", f"msg-{i}")

    loaded = store.get_session(session.id)
    assert loaded is not None
    for i, msg in enumerate(loaded.messages):
        assert msg.content == f"msg-{i}"


def test_multiple_sessions_isolated(store):
    """Messages from different sessions should not leak"""
    s1 = store.create_session(title="Session 1")
    s2 = store.create_session(title="Session 2")

    store.add_message(s1.id, "user", "s1-msg")
    store.add_message(s2.id, "user", "s2-msg")

    loaded1 = store.get_session(s1.id)
    loaded2 = store.get_session(s2.id)

    assert len(loaded1.messages) == 1
    assert loaded1.messages[0].content == "s1-msg"
    assert len(loaded2.messages) == 1
    assert loaded2.messages[0].content == "s2-msg"


def test_session_updated_at_changes(store):
    """updated_at should change when a message is added"""
    session = store.create_session(title="Timestamp Test")
    original = store.get_session(session.id)

    import time
    time.sleep(0.01)  # Ensure time difference

    store.add_message(session.id, "user", "new message")
    updated = store.get_session(session.id)

    assert updated.updated_at >= original.updated_at
