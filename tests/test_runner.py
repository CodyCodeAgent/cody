"""Tests for AgentRunner session integration"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic_ai.messages import ModelRequest, ModelResponse

from cody.core.runner import AgentRunner
from cody.core.session import Message, SessionStore


# ── messages_to_history ──────────────────────────────────────────────────────


def test_messages_to_history_empty():
    result = AgentRunner.messages_to_history([])
    assert result == []


def test_messages_to_history_user_message():
    msgs = [Message(role="user", content="hello")]
    result = AgentRunner.messages_to_history(msgs)
    assert len(result) == 1
    assert isinstance(result[0], ModelRequest)
    assert result[0].parts[0].content == "hello"


def test_messages_to_history_assistant_message():
    msgs = [Message(role="assistant", content="hi there")]
    result = AgentRunner.messages_to_history(msgs)
    assert len(result) == 1
    assert isinstance(result[0], ModelResponse)
    assert result[0].parts[0].content == "hi there"


def test_messages_to_history_conversation():
    msgs = [
        Message(role="user", content="what is 1+1?"),
        Message(role="assistant", content="2"),
        Message(role="user", content="and 2+2?"),
        Message(role="assistant", content="4"),
    ]
    result = AgentRunner.messages_to_history(msgs)
    assert len(result) == 4
    assert isinstance(result[0], ModelRequest)
    assert isinstance(result[1], ModelResponse)
    assert isinstance(result[2], ModelRequest)
    assert isinstance(result[3], ModelResponse)
    assert result[3].parts[0].content == "4"


def test_messages_to_history_skips_unknown_roles():
    msgs = [
        Message(role="user", content="hello"),
        Message(role="system", content="ignored"),
        Message(role="assistant", content="hi"),
    ]
    result = AgentRunner.messages_to_history(msgs)
    assert len(result) == 2


# ── prepare_session ──────────────────────────────────────────────────────────


def test_prepare_session_creates_new(tmp_path):
    store = SessionStore(db_path=tmp_path / "test.db")

    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = MagicMock()
        runner.config.model = "test-model"
        runner.workdir = tmp_path

    sid, history = runner.prepare_session(store)
    assert sid is not None
    assert len(sid) == 12
    assert history is None

    # Session should exist in store
    session = store.get_session(sid)
    assert session is not None
    assert session.model == "test-model"
    assert session.workdir == str(tmp_path)


def test_prepare_session_loads_existing(tmp_path):
    store = SessionStore(db_path=tmp_path / "test.db")
    session = store.create_session(title="test")
    store.add_message(session.id, "user", "hello")
    store.add_message(session.id, "assistant", "hi")

    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = MagicMock()
        runner.config.model = "test-model"
        runner.workdir = tmp_path

    sid, history = runner.prepare_session(store, session.id)
    assert sid == session.id
    assert history is not None
    assert len(history) == 2
    assert isinstance(history[0], ModelRequest)
    assert isinstance(history[1], ModelResponse)


def test_prepare_session_empty_existing(tmp_path):
    store = SessionStore(db_path=tmp_path / "test.db")
    session = store.create_session(title="empty")

    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = MagicMock()
        runner.config.model = "test-model"
        runner.workdir = tmp_path

    sid, history = runner.prepare_session(store, session.id)
    assert sid == session.id
    assert history is None  # empty session → no history


def test_prepare_session_not_found(tmp_path):
    store = SessionStore(db_path=tmp_path / "test.db")

    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = MagicMock()
        runner.config.model = "test-model"
        runner.workdir = tmp_path

    with pytest.raises(ValueError, match="Session not found"):
        runner.prepare_session(store, "nonexistent_id")


# ── run_with_session ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_with_session_new(tmp_path):
    """run_with_session creates session, runs agent, persists messages"""
    store = SessionStore(db_path=tmp_path / "test.db")

    mock_result = MagicMock()
    mock_result.output = "I created hello.py"

    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = MagicMock()
        runner.config.model = "test-model"
        runner.workdir = tmp_path
        runner.skill_manager = MagicMock()
        runner.run = AsyncMock(return_value=mock_result)

    result, sid = await runner.run_with_session("create hello.py", store)

    assert result.output == "I created hello.py"
    assert sid is not None

    # Verify messages persisted
    session = store.get_session(sid)
    assert len(session.messages) == 2
    assert session.messages[0].role == "user"
    assert session.messages[0].content == "create hello.py"
    assert session.messages[1].role == "assistant"
    assert session.messages[1].content == "I created hello.py"


@pytest.mark.asyncio
async def test_run_with_session_continue(tmp_path):
    """run_with_session loads history and appends new messages"""
    store = SessionStore(db_path=tmp_path / "test.db")
    session = store.create_session(title="ongoing")
    store.add_message(session.id, "user", "hello")
    store.add_message(session.id, "assistant", "hi there")

    mock_result = MagicMock()
    mock_result.output = "sure, I can help"

    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = MagicMock()
        runner.config.model = "test-model"
        runner.workdir = tmp_path
        runner.skill_manager = MagicMock()
        runner.run = AsyncMock(return_value=mock_result)

    result, sid = await runner.run_with_session("help me", store, session.id)

    assert sid == session.id
    assert result.output == "sure, I can help"

    # Should have 4 messages now (2 old + 2 new)
    updated = store.get_session(sid)
    assert len(updated.messages) == 4
    assert updated.messages[2].content == "help me"
    assert updated.messages[3].content == "sure, I can help"

    # Verify history was passed to run()
    call_kwargs = runner.run.call_args
    history = call_kwargs.kwargs.get("message_history") or call_kwargs.args[1]
    assert len(history) == 2  # the original 2 messages


@pytest.mark.asyncio
async def test_run_with_session_not_found(tmp_path):
    """run_with_session raises ValueError for bad session_id"""
    store = SessionStore(db_path=tmp_path / "test.db")

    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = MagicMock()
        runner.config.model = "test-model"
        runner.workdir = tmp_path

    with pytest.raises(ValueError, match="Session not found"):
        await runner.run_with_session("hello", store, "bad_id")
