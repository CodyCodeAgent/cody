"""Tests for Terminal UI"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cody.tui import CodyTUI, MessageBubble, StreamBubble, run_tui


# ── MessageBubble ────────────────────────────────────────────────────────────


def test_message_bubble_user():
    bubble = MessageBubble("user", "hello world")
    formatted = MessageBubble._format_message("user", "hello world")
    assert "You" in formatted
    assert "hello world" in formatted
    assert bubble.role == "user"
    assert bubble.content_text == "hello world"


def test_message_bubble_assistant():
    bubble = MessageBubble("assistant", "I can help!")
    formatted = MessageBubble._format_message("assistant", "I can help!")
    assert "Cody" in formatted
    assert "I can help!" in formatted
    assert bubble.role == "assistant"


def test_message_bubble_system():
    bubble = MessageBubble("system", "info message")
    formatted = MessageBubble._format_message("system", "info message")
    assert "system" in formatted
    assert "info message" in formatted
    assert bubble.role == "system"


# ── StreamBubble ─────────────────────────────────────────────────────────────


def test_stream_bubble_append():
    bubble = StreamBubble()
    bubble.append("Hello")
    bubble.append(" world")
    assert bubble.full_text == "Hello world"


def test_stream_bubble_empty():
    bubble = StreamBubble()
    assert bubble.full_text == ""


# ── CodyTUI construction ────────────────────────────────────────────────────


def test_tui_default_construction():
    app = CodyTUI()
    assert app._workdir == Path.cwd().resolve()
    assert app._model_override is None
    assert app._session_id_arg is None
    assert app._continue_last is False


def test_tui_with_options(tmp_path):
    app = CodyTUI(
        model="test-model",
        workdir=tmp_path,
        session_id="abc123",
        continue_last=True,
    )
    assert app._model_override == "test-model"
    assert app._workdir == tmp_path.resolve()
    assert app._session_id_arg == "abc123"
    assert app._continue_last is True


# ── Helper to set up TUI mocks ──────────────────────────────────────────────


def _setup_tui_mocks(mock_client_cls, mock_config_load):
    """Common mock setup for TUI tests."""
    mock_config = MagicMock()
    mock_config.model = "test-model"
    mock_config.model_api_key = None
    mock_config.model_base_url = None
    mock_config_load.return_value = mock_config

    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    mock_store = MagicMock()
    mock_session = MagicMock()
    mock_session.id = "test123"
    mock_session.messages = []
    mock_store.get_latest_session.return_value = None
    mock_store.create_session.return_value = mock_session
    mock_store.get_message_count.return_value = 0
    mock_client.get_session_store.return_value = mock_store
    mock_client.get_message_count.return_value = 0

    mock_client_cls.messages_to_history.return_value = []

    return mock_config, mock_client, mock_store, mock_session


# ── CodyTUI async pilot tests ───────────────────────────────────────────────


@pytest.mark.asyncio
@patch("cody.tui.app.Config.load")
@patch("cody.tui.app.AsyncCodyClient")
async def test_tui_mounts(mock_client_cls, mock_config_load, tmp_path):
    """TUI app mounts without crashing."""
    _setup_tui_mocks(mock_client_cls, mock_config_load)

    app = CodyTUI(workdir=tmp_path)
    async with app.run_test():
        # Verify the app mounted and has the expected widgets
        assert app.query_one("#chat-scroll") is not None
        assert app.query_one("#prompt-input") is not None
        assert app.query_one("#status-line") is not None


@pytest.mark.asyncio
@patch("cody.tui.app.Config.load")
@patch("cody.tui.app.AsyncCodyClient")
async def test_tui_slash_help(mock_client_cls, mock_config_load, tmp_path):
    """Typing /help shows help text."""
    _setup_tui_mocks(mock_client_cls, mock_config_load)

    app = CodyTUI(workdir=tmp_path)
    async with app.run_test() as pilot:
        inp = app.query_one("#prompt-input")
        inp.value = "/help"
        await pilot.press("enter")
        await pilot.pause()

        # Should have mounted message bubbles including help
        bubbles = app.query(MessageBubble)
        assert len(bubbles) >= 1


@pytest.mark.asyncio
@patch("cody.tui.app.Config.load")
@patch("cody.tui.app.AsyncCodyClient")
async def test_tui_new_session(mock_client_cls, mock_config_load, tmp_path):
    """Ctrl+N creates a new session."""
    mock_config, mock_client, mock_store, mock_session = _setup_tui_mocks(
        mock_client_cls, mock_config_load
    )
    mock_session.id = "session1"

    new_session = MagicMock()
    new_session.id = "session2"
    new_session.messages = []

    mock_store.create_session.side_effect = [mock_session, new_session]

    app = CodyTUI(workdir=tmp_path)
    async with app.run_test() as pilot:
        assert app._session_id == "session1"

        # Trigger new session
        app.action_new_session()
        await pilot.pause()

        assert app._session_id == "session2"


@pytest.mark.asyncio
@patch("cody.tui.app.Config.load")
@patch("cody.tui.app.AsyncCodyClient")
async def test_tui_slash_clear(mock_client_cls, mock_config_load, tmp_path):
    """/clear removes chat bubbles."""
    _setup_tui_mocks(mock_client_cls, mock_config_load)

    app = CodyTUI(workdir=tmp_path)
    async with app.run_test() as pilot:
        # Type /clear
        inp = app.query_one("#prompt-input")
        inp.value = "/clear"
        await pilot.press("enter")
        await pilot.pause()

        # Should have the "Screen cleared" bubble
        bubbles = app.query(MessageBubble)
        assert len(bubbles) >= 1


# ── run_tui entry point ─────────────────────────────────────────────────────


def test_run_tui_creates_app():
    """run_tui should create and run a CodyTUI app."""
    with patch.object(CodyTUI, "run") as mock_run:
        run_tui(model="test", workdir="/tmp")
        mock_run.assert_called_once()


# ── Additional TUI tests (S5) ─────────────────────────────────────────────────


def test_stream_bubble_dirty_flag():
    """StreamBubble marks dirty on append."""
    bubble = StreamBubble()
    assert not bubble._dirty
    bubble.append("hi")
    assert bubble._dirty


def test_message_bubble_unknown_role():
    """Unknown roles should still render."""
    bubble = MessageBubble("tool", "tool output")
    formatted = MessageBubble._format_message("tool", "tool output")
    assert "tool" in formatted
    assert bubble.role == "tool"


def test_tui_with_extra_roots(tmp_path):
    app = CodyTUI(
        workdir=tmp_path,
        extra_roots=[str(tmp_path / "extra")],
    )
    assert len(app._extra_roots) == 1


@pytest.mark.asyncio
@patch("cody.tui.app.Config.load")
@patch("cody.tui.app.AsyncCodyClient")
async def test_tui_slash_unknown(mock_client_cls, mock_config_load, tmp_path):
    """Unknown slash commands show an error."""
    _setup_tui_mocks(mock_client_cls, mock_config_load)

    app = CodyTUI(workdir=tmp_path)
    async with app.run_test() as pilot:
        inp = app.query_one("#prompt-input")
        inp.value = "/foobar"
        await pilot.press("enter")
        await pilot.pause()

        bubbles = app.query(MessageBubble)
        assert len(bubbles) >= 1


def test_tui_max_bubbles_constant():
    """_MAX_BUBBLES should be a reasonable number."""
    assert CodyTUI._MAX_BUBBLES >= 50
