"""Tests for AgentRunner session integration"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from cody.core.config import Config
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


# ── _compact_history_if_needed ───────────────────────────────────────────────


def test_compact_history_returns_tuple_no_compaction():
    """_compact_history_if_needed returns (history, None) when no compaction needed."""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)

    history = [
        ModelRequest(parts=[UserPromptPart(content="hello")]),
        ModelResponse(parts=[TextPart(content="hi")]),
    ]
    result_history, compact_result = runner._compact_history_if_needed(history)
    assert result_history is history
    assert compact_result is None


def test_compact_history_returns_tuple_none_input():
    """_compact_history_if_needed returns (None, None) for None input."""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)

    result_history, compact_result = runner._compact_history_if_needed(None)
    assert result_history is None
    assert compact_result is None


def test_compact_history_returns_compact_result():
    """_compact_history_if_needed returns CompactResult when compaction happens."""
    from pydantic_ai.messages import TextPart, UserPromptPart
    from cody.core.context import CompactResult

    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)

    # Create enough messages to trigger compaction
    history = []
    for i in range(20):
        history.append(ModelRequest(parts=[UserPromptPart(content=f"msg {i} " * 200)]))
        history.append(ModelResponse(parts=[TextPart(content=f"reply {i} " * 200)]))

    result_history, compact_result = runner._compact_history_if_needed(history, max_tokens=100)
    assert compact_result is not None
    assert isinstance(compact_result, CompactResult)
    assert compact_result.original_messages == 40
    assert compact_result.compacted_messages == 5
    assert compact_result.estimated_tokens_saved > 0
    assert len(result_history) == 5


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


# ── _resolve_model ──────────────────────────────────────────────────────────


def test_resolve_model_default_string():
    """Without base_url, _resolve_model returns the model string as-is"""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = Config(model="anthropic:claude-sonnet-4-0")

    result = runner._resolve_model()
    assert result == "anthropic:claude-sonnet-4-0"


def test_resolve_model_with_base_url():
    """With base_url, _resolve_model returns an OpenAIModel instance"""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = Config(
            model="glm-4",
            model_base_url="https://open.bigmodel.cn/api/paas/v4/",
            model_api_key="sk-test",
        )

    result = runner._resolve_model()
    # Should be an OpenAIModel, not a string
    assert not isinstance(result, str)
    assert hasattr(result, "model_name") or hasattr(result, "name")


def test_resolve_model_base_url_without_api_key():
    """With base_url but no api_key, _resolve_model uses fallback key"""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = Config(
            model="qwen-coder-plus",
            model_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

    # Should not raise — falls back to "not-set" placeholder
    result = runner._resolve_model()
    assert not isinstance(result, str)


def test_resolve_model_with_claude_oauth_token():
    """With claude_oauth_token, _resolve_model returns an AnthropicModel"""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = Config(
            model="anthropic:claude-sonnet-4-0",
            claude_oauth_token="oauth-test-token",
        )

    result = runner._resolve_model()
    # Should be an AnthropicModel, not a string
    assert not isinstance(result, str)
    from pydantic_ai.models.anthropic import AnthropicModel
    assert isinstance(result, AnthropicModel)


def test_resolve_model_oauth_strips_prefix():
    """OAuth path strips 'anthropic:' prefix from model name"""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = Config(
            model="anthropic:claude-sonnet-4-0",
            claude_oauth_token="oauth-test-token",
        )

    result = runner._resolve_model()
    assert not isinstance(result, str)
    # The model_name passed to AnthropicModel should not have the prefix
    assert "anthropic:" not in str(result.model_name)


def test_resolve_model_oauth_without_prefix():
    """OAuth path works when model name has no 'anthropic:' prefix"""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = Config(
            model="claude-sonnet-4-0",
            claude_oauth_token="oauth-test-token",
        )

    result = runner._resolve_model()
    assert not isinstance(result, str)
    from pydantic_ai.models.anthropic import AnthropicModel
    assert isinstance(result, AnthropicModel)


def test_resolve_model_base_url_takes_priority_over_oauth():
    """model_base_url takes priority over claude_oauth_token"""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = Config(
            model="glm-4",
            model_base_url="https://open.bigmodel.cn/api/paas/v4/",
            model_api_key="sk-test",
            claude_oauth_token="oauth-test-token",
        )

    result = runner._resolve_model()
    # Should use OpenAI path, not Anthropic OAuth
    assert not isinstance(result, str)
    from pydantic_ai.models.openai import OpenAIChatModel
    assert isinstance(result, OpenAIChatModel)


# ── Coding Plan _resolve_model ─────────────────────────────────────────────


def test_resolve_model_coding_plan_openai():
    """Coding Plan with openai protocol returns OpenAIChatModel"""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = Config(
            model="qwen3.5",
            coding_plan_key="sk-sp-test123",
            coding_plan_protocol="openai",
        )

    result = runner._resolve_model()
    assert not isinstance(result, str)
    from pydantic_ai.models.openai import OpenAIChatModel
    assert isinstance(result, OpenAIChatModel)


def test_resolve_model_coding_plan_anthropic():
    """Coding Plan with anthropic protocol returns AnthropicModel"""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = Config(
            model="claude-sonnet-4-0",
            coding_plan_key="sk-sp-test123",
            coding_plan_protocol="anthropic",
        )

    result = runner._resolve_model()
    assert not isinstance(result, str)
    from pydantic_ai.models.anthropic import AnthropicModel
    assert isinstance(result, AnthropicModel)


def test_resolve_model_coding_plan_anthropic_strips_prefix():
    """Coding Plan anthropic protocol strips 'anthropic:' prefix"""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = Config(
            model="anthropic:claude-sonnet-4-0",
            coding_plan_key="sk-sp-test123",
            coding_plan_protocol="anthropic",
        )

    result = runner._resolve_model()
    assert not isinstance(result, str)
    assert "anthropic:" not in str(result.model_name)


def test_resolve_model_coding_plan_default_protocol():
    """Coding Plan defaults to openai protocol"""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = Config(
            model="qwen3.5",
            coding_plan_key="sk-sp-test123",
        )

    result = runner._resolve_model()
    assert not isinstance(result, str)
    from pydantic_ai.models.openai import OpenAIChatModel
    assert isinstance(result, OpenAIChatModel)


def test_resolve_model_coding_plan_takes_priority():
    """coding_plan_key takes priority over model_base_url and oauth"""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = Config(
            model="qwen3.5",
            coding_plan_key="sk-sp-test123",
            model_base_url="https://other.api.com/v1",
            model_api_key="sk-other",
            claude_oauth_token="oauth-token",
        )

    result = runner._resolve_model()
    assert not isinstance(result, str)
    from pydantic_ai.models.openai import OpenAIChatModel
    assert isinstance(result, OpenAIChatModel)
