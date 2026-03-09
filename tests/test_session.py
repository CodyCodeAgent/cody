"""Tests for session management"""

import pytest
from cody.core.prompt import ImageData
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


# ── Image storage ────────────────────────────────────────────────────────────


def test_add_message_with_images(store):
    """Messages with images are stored and retrieved correctly."""
    session = store.create_session(title="Image Test")
    imgs = [ImageData(data="aGVsbG8=", media_type="image/png", filename="screenshot.png")]
    store.add_message(session.id, "user", "check this", images=imgs)

    loaded = store.get_session(session.id)
    assert len(loaded.messages) == 1
    assert loaded.messages[0].content == "check this"
    assert len(loaded.messages[0].images) == 1
    assert loaded.messages[0].images[0].media_type == "image/png"
    assert loaded.messages[0].images[0].filename == "screenshot.png"
    assert loaded.messages[0].images[0].data == "aGVsbG8="


def test_add_message_without_images_backward_compat(store):
    """Messages without images still work (backward compat)."""
    session = store.create_session(title="Text Only")
    store.add_message(session.id, "user", "just text")

    loaded = store.get_session(session.id)
    assert loaded.messages[0].content == "just text"
    assert loaded.messages[0].images == []


def test_add_message_multiple_images(store):
    """Multiple images in a single message."""
    session = store.create_session(title="Multi Image")
    imgs = [
        ImageData(data="aGVsbG8=", media_type="image/png"),
        ImageData(data="d29ybGQ=", media_type="image/jpeg", filename="photo.jpg"),
    ]
    store.add_message(session.id, "user", "compare these", images=imgs)

    loaded = store.get_session(session.id)
    assert len(loaded.messages[0].images) == 2
    assert loaded.messages[0].images[0].media_type == "image/png"
    assert loaded.messages[0].images[1].media_type == "image/jpeg"
    assert loaded.messages[0].images[1].filename == "photo.jpg"


def test_mixed_messages_with_and_without_images(store):
    """Conversation with both image and text-only messages."""
    session = store.create_session(title="Mixed")
    imgs = [ImageData(data="aGVsbG8=", media_type="image/png")]
    store.add_message(session.id, "user", "look at this", images=imgs)
    store.add_message(session.id, "assistant", "I see an image")
    store.add_message(session.id, "user", "thanks")

    loaded = store.get_session(session.id)
    assert len(loaded.messages) == 3
    assert len(loaded.messages[0].images) == 1
    assert loaded.messages[1].images == []
    assert loaded.messages[2].images == []


# ── Compaction checkpoint ─────────────────────────────────────────────────────


def test_save_and_load_compaction_checkpoint(store):
    """Compaction summary and up_to are persisted and loaded."""
    session = store.create_session(title="Compact Test")
    store.add_message(session.id, "user", "msg1")
    store.add_message(session.id, "assistant", "msg2")
    store.add_message(session.id, "user", "msg3")

    last_id = store.get_last_message_id(session.id)
    assert last_id is not None

    store.save_compaction(session.id, "summary of conversation", last_id)

    loaded = store.get_session(session.id)
    assert loaded.compacted_summary == "summary of conversation"
    assert loaded.compacted_up_to == last_id


def test_get_messages_after(store):
    """get_messages_after returns only messages with id > after_id."""
    session = store.create_session(title="After Test")
    store.add_message(session.id, "user", "old1")
    store.add_message(session.id, "assistant", "old2")

    cutoff_id = store.get_last_message_id(session.id)

    store.add_message(session.id, "user", "new1")
    store.add_message(session.id, "assistant", "new2")

    after = store.get_messages_after(session.id, cutoff_id)
    assert len(after) == 2
    assert after[0].content == "new1"
    assert after[1].content == "new2"


def test_get_last_message_id(store):
    """get_last_message_id returns the rowid of the most recent message."""
    session = store.create_session(title="Last ID Test")
    assert store.get_last_message_id(session.id) is None

    store.add_message(session.id, "user", "first")
    id1 = store.get_last_message_id(session.id)
    assert id1 is not None

    store.add_message(session.id, "assistant", "second")
    id2 = store.get_last_message_id(session.id)
    assert id2 > id1


def test_compaction_checkpoint_defaults_to_none(store):
    """New sessions have no compaction checkpoint."""
    session = store.create_session(title="No Compact")
    loaded = store.get_session(session.id)
    assert loaded.compacted_summary is None
    assert loaded.compacted_up_to is None


def test_compaction_checkpoint_update_overwrites(store):
    """Saving compaction again overwrites the previous checkpoint."""
    session = store.create_session(title="Overwrite Test")
    store.add_message(session.id, "user", "msg1")
    id1 = store.get_last_message_id(session.id)
    store.save_compaction(session.id, "summary v1", id1)

    store.add_message(session.id, "user", "msg2")
    store.add_message(session.id, "assistant", "msg3")
    id2 = store.get_last_message_id(session.id)
    store.save_compaction(session.id, "summary v2", id2)

    loaded = store.get_session(session.id)
    assert loaded.compacted_summary == "summary v2"
    assert loaded.compacted_up_to == id2
