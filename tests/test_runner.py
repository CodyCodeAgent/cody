"""Tests for AgentRunner session integration"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from cody.core.config import Config
from cody.core.prompt import ImageData, MultimodalPrompt
from cody.core.runner import AgentRunner, _build_allowed_roots
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


def test_resolve_model_no_api_key_raises():
    """Without api_key, _resolve_model raises ValueError"""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = Config(model="anthropic:claude-sonnet-4-0")

    with pytest.raises(ValueError, match="model_api_key is required"):
        runner._resolve_model()


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


def test_resolve_model_api_key_anthropic():
    """With model_api_key (no base_url), _resolve_model returns an AnthropicModel"""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = Config(
            model="anthropic:claude-sonnet-4-0",
            model_api_key="sk-ant-test-key",
        )

    result = runner._resolve_model()
    assert not isinstance(result, str)
    from pydantic_ai.models.anthropic import AnthropicModel
    assert isinstance(result, AnthropicModel)


def test_resolve_model_api_key_strips_prefix():
    """Anthropic API key path strips 'anthropic:' prefix from model name"""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = Config(
            model="anthropic:claude-sonnet-4-0",
            model_api_key="sk-ant-test-key",
        )

    result = runner._resolve_model()
    assert not isinstance(result, str)
    assert "anthropic:" not in str(result.model_name)


def test_resolve_model_base_url_takes_priority_over_api_key():
    """model_base_url takes priority over model_api_key for Anthropic"""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = Config(
            model="glm-4",
            model_base_url="https://open.bigmodel.cn/api/paas/v4/",
            model_api_key="sk-test",
        )

    result = runner._resolve_model()
    assert not isinstance(result, str)
    from pydantic_ai.models.openai import OpenAIChatModel
    assert isinstance(result, OpenAIChatModel)


# ── model_base_url _resolve_model ──────────────────────────────────────────


def test_resolve_model_base_url():
    """model_base_url returns OpenAIChatModel"""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = Config(
            model="qwen3.5",
            model_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model_api_key="sk-test123",
        )

    result = runner._resolve_model()
    assert not isinstance(result, str)
    from pydantic_ai.models.openai import OpenAIChatModel
    assert isinstance(result, OpenAIChatModel)


def test_resolve_model_base_url_deepseek():
    """model_base_url with DeepSeek returns OpenAIChatModel"""
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        runner.config = Config(
            model="deepseek-chat",
            model_base_url="https://api.deepseek.com/v1",
            model_api_key="sk-test123",
        )

    result = runner._resolve_model()
    assert not isinstance(result, str)
    from pydantic_ai.models.openai import OpenAIChatModel
    assert isinstance(result, OpenAIChatModel)


# ── _build_allowed_roots ──────────────────────────────────────────────────────


def test_build_allowed_roots_empty(tmp_path):
    """No config roots and no extra roots → empty list."""
    result = _build_allowed_roots(tmp_path, [], [])
    assert result == []


def test_build_allowed_roots_absolute_path(tmp_path):
    """Absolute string in config → resolved Path returned."""
    other = tmp_path / "other"
    other.mkdir()
    result = _build_allowed_roots(tmp_path, [str(other)], [])
    assert len(result) == 1
    assert result[0] == other.resolve()


def test_build_allowed_roots_extra_roots(tmp_path):
    """Extra runtime roots are merged in."""
    other = tmp_path / "other"
    other.mkdir()
    result = _build_allowed_roots(tmp_path, [], [other])
    assert len(result) == 1
    assert result[0] == other.resolve()


def test_build_allowed_roots_deduplicates(tmp_path):
    """Same path in config and extra_roots is deduplicated."""
    other = tmp_path / "other"
    other.mkdir()
    result = _build_allowed_roots(tmp_path, [str(other)], [other])
    assert len(result) == 1


def test_build_allowed_roots_skips_workdir_itself(tmp_path):
    """workdir in config roots is silently dropped."""
    result = _build_allowed_roots(tmp_path, [str(tmp_path)], [])
    assert result == []


def test_build_allowed_roots_rejects_relative_config_path(tmp_path):
    """Relative paths in config roots raise ValueError."""
    with pytest.raises(ValueError, match="absolute paths"):
        _build_allowed_roots(tmp_path, ["../relative"], [])


# ── _to_pydantic_prompt ─────────────────────────────────────────────────────


def test_to_pydantic_prompt_str():
    """Plain str prompt passes through unchanged."""
    result = AgentRunner._to_pydantic_prompt("hello")
    assert result == "hello"


def test_to_pydantic_prompt_multimodal():
    """MultimodalPrompt converts to list with ImageUrl."""
    img = ImageData(data="aGVsbG8=", media_type="image/png")
    prompt = MultimodalPrompt(text="analyze", images=[img])
    result = AgentRunner._to_pydantic_prompt(prompt)
    assert isinstance(result, list)
    assert result[0] == "analyze"
    assert len(result) == 2
    # Second item should be ImageUrl with data URI
    from pydantic_ai.messages import ImageUrl
    assert isinstance(result[1], ImageUrl)
    assert result[1].url.startswith("data:image/png;base64,")


def test_to_pydantic_prompt_multimodal_multiple_images():
    """MultimodalPrompt with multiple images produces correct list."""
    img1 = ImageData(data="aGVsbG8=", media_type="image/png")
    img2 = ImageData(data="d29ybGQ=", media_type="image/jpeg")
    prompt = MultimodalPrompt(text="compare", images=[img1, img2])
    result = AgentRunner._to_pydantic_prompt(prompt)
    assert isinstance(result, list)
    assert len(result) == 3  # text + 2 images


def test_to_pydantic_prompt_empty_text_multimodal():
    """MultimodalPrompt with empty text still works."""
    img = ImageData(data="aGVsbG8=", media_type="image/png")
    prompt = MultimodalPrompt(text="", images=[img])
    result = AgentRunner._to_pydantic_prompt(prompt)
    assert isinstance(result, list)
    assert len(result) == 1  # only ImageUrl, no empty text


# ── messages_to_history with images ──────────────────────────────────────────


def test_messages_to_history_with_images():
    """Messages with images reconstruct multimodal UserPromptPart."""
    imgs = [ImageData(data="aGVsbG8=", media_type="image/png")]
    msgs = [Message(role="user", content="look at this", images=imgs)]
    result = AgentRunner.messages_to_history(msgs)
    assert len(result) == 1
    assert isinstance(result[0], ModelRequest)
    # The content should be a list (multimodal)
    part = result[0].parts[0]
    content = part.content
    assert isinstance(content, list)
    assert len(content) == 2  # text + ImageUrl


def test_messages_to_history_mixed_with_and_without_images():
    """Mixed messages: some with images, some without."""
    imgs = [ImageData(data="aGVsbG8=", media_type="image/png")]
    msgs = [
        Message(role="user", content="look at this", images=imgs),
        Message(role="assistant", content="I see it"),
        Message(role="user", content="thanks"),
    ]
    result = AgentRunner.messages_to_history(msgs)
    assert len(result) == 3
    # First message: multimodal
    assert isinstance(result[0].parts[0].content, list)
    # Third message: plain text
    assert isinstance(result[2].parts[0].content, str)
