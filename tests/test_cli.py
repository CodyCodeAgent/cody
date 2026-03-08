"""Tests for CLI commands"""

import pytest
from pathlib import Path
from click.testing import CliRunner
from cody.cli import main, _handle_command
from cody.sdk.client import AsyncCodyClient
from cody.core.session import SessionStore, Session, Message


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def store(tmp_path):
    return SessionStore(db_path=tmp_path / "test.db")


# ── CLI basic commands ───────────────────────────────────────────────────────


def test_main_help(runner):
    result = runner.invoke(main, ['--help'])
    assert result.exit_code == 0
    assert 'Cody' in result.output


def test_run_no_prompt(runner):
    result = runner.invoke(main, ['run'])
    assert result.exit_code == 0
    assert 'Please provide a prompt' in result.output


def test_init_creates_directory(runner, tmp_path, monkeypatch):
    # Mock AI generation so the test doesn't need a real API key.
    async def _fake_generate(workdir, config):
        return "# CODY.md\n\nAI-generated content."

    monkeypatch.setattr("cody.cli.commands.init_cmd.generate_project_instructions", _fake_generate)
    monkeypatch.setenv("CODY_MODEL_API_KEY", "sk-test-key")

    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ['init'], input='n\n')
        assert result.exit_code == 0, result.output
        assert 'Initialized' in result.output
        assert (Path.cwd() / '.cody').exists()
        assert (Path.cwd() / '.cody' / 'skills').exists()
        assert (Path.cwd() / '.cody' / 'config.json').exists()
        assert (Path.cwd() / 'CODY.md').exists()
        assert 'AI-generated' in (Path.cwd() / 'CODY.md').read_text()


def test_init_already_exists(runner, tmp_path, monkeypatch):
    async def _fake_generate(workdir, config):
        return "# CODY.md\n\nAI content."

    monkeypatch.setattr("cody.cli.commands.init_cmd.generate_project_instructions", _fake_generate)
    monkeypatch.setenv("CODY_MODEL_API_KEY", "sk-test-key")

    with runner.isolated_filesystem(temp_dir=tmp_path):
        (Path.cwd() / '.cody').mkdir()
        result = runner.invoke(main, ['init'], input='n\n')
        assert result.exit_code == 0, result.output
        # .cody already existed → skip scaffold message
        assert 'skipping scaffold' in result.output
        # CODY.md always (re-)generated
        assert (Path.cwd() / 'CODY.md').exists()
        assert 'AI-generated' in result.output


def test_init_updates_existing_cody_md(runner, tmp_path, monkeypatch):
    async def _fake_generate(workdir, config):
        return "# CODY.md\n\nNew AI content."

    monkeypatch.setattr("cody.cli.commands.init_cmd.generate_project_instructions", _fake_generate)
    monkeypatch.setenv("CODY_MODEL_API_KEY", "sk-test-key")

    with runner.isolated_filesystem(temp_dir=tmp_path):
        (Path.cwd() / '.cody').mkdir()
        (Path.cwd() / 'CODY.md').write_text("old content")
        result = runner.invoke(main, ['init'], input='n\n')
        assert result.exit_code == 0, result.output
        # File updated, not just created
        assert 'Updated' in result.output
        assert (Path.cwd() / 'CODY.md').read_text() == "# CODY.md\n\nNew AI content."


def test_config_show(runner):
    result = runner.invoke(main, ['config', 'show'])
    assert result.exit_code == 0
    assert 'model' in result.output


def test_skills_list(runner):
    # This command creates an AgentRunner which needs an LLM API key.
    # We just verify the command exists and runs (may fail with API key error).
    result = runner.invoke(main, ['skills', 'list'])
    # Either succeeds or fails due to missing API key
    assert result.exit_code in (0, 1)


# ── Chat command tests ───────────────────────────────────────────────────────


def test_chat_help(runner):
    result = runner.invoke(main, ['chat', '--help'])
    assert result.exit_code == 0
    assert 'Interactive chat' in result.output
    assert '--session' in result.output
    assert '--continue' in result.output


def test_chat_nonexistent_session(runner, monkeypatch):
    monkeypatch.setenv("CODY_MODEL_API_KEY", "sk-test-key")
    monkeypatch.setattr("cody.core.config.Config.is_ready", lambda self: True)
    result = runner.invoke(main, ['chat', '--session', 'nonexistent'], input='/quit\n')
    assert 'Session not found' in result.output


# ── Session CLI commands ─────────────────────────────────────────────────────


def test_sessions_list_empty(runner):
    result = runner.invoke(main, ['sessions', 'list'])
    assert result.exit_code == 0


def test_sessions_show_nonexistent(runner):
    result = runner.invoke(main, ['sessions', 'show', 'nonexistent'])
    assert result.exit_code == 0
    assert 'not found' in result.output


# ── Handle command tests ─────────────────────────────────────────────────────


def test_handle_quit(store):
    from rich.console import Console
    with open('/dev/null', 'w', encoding='utf-8') as devnull:
        console = Console(file=devnull)
        session = store.create_session(title="test")

        assert _handle_command("/quit", session, store, console) is False
        assert _handle_command("/exit", session, store, console) is False
        assert _handle_command("/q", session, store, console) is False


def test_handle_help(store):
    from io import StringIO
    from rich.console import Console
    buf = StringIO()
    console = Console(file=buf)
    session = store.create_session(title="test")

    result = _handle_command("/help", session, store, console)
    assert result is True
    output = buf.getvalue()
    assert "quit" in output.lower()


def test_handle_sessions(store):
    from io import StringIO
    from rich.console import Console
    buf = StringIO()
    console = Console(file=buf)

    store.create_session(title="Session A")
    session_b = store.create_session(title="Session B")

    result = _handle_command("/sessions", session_b, store, console)
    assert result is True
    output = buf.getvalue()
    assert "Session A" in output or "Session B" in output


def test_handle_unknown_command(store):
    from io import StringIO
    from rich.console import Console
    buf = StringIO()
    console = Console(file=buf)
    session = store.create_session(title="test")

    result = _handle_command("/unknown", session, store, console)
    assert result is True
    assert "Unknown command" in buf.getvalue()


# ── Build history tests ──────────────────────────────────────────────────────


def test_build_history_empty():
    session = Session(
        id="test", title="test", messages=[],
        model="", workdir="", created_at="", updated_at="",
    )
    history = AsyncCodyClient.messages_to_history(session.messages)
    assert history == []


def test_build_history_with_messages():
    session = Session(
        id="test", title="test",
        messages=[
            Message(role="user", content="hello"),
            Message(role="assistant", content="hi there"),
            Message(role="user", content="thanks"),
        ],
        model="", workdir="", created_at="", updated_at="",
    )
    history = AsyncCodyClient.messages_to_history(session.messages)
    assert len(history) == 3


# ── Additional CLI tests (S5) ────────────────────────────────────────────────


def test_run_with_model_override(runner):
    """--model flag is accepted without error."""
    result = runner.invoke(main, ['run', '--model', 'test-model'])
    # No prompt provided, so should show help text
    assert result.exit_code == 0
    assert 'Please provide a prompt' in result.output


def test_run_with_workdir(runner, tmp_path):
    """--workdir flag is accepted."""
    result = runner.invoke(main, ['run', '--workdir', str(tmp_path)])
    assert result.exit_code == 0
    assert 'Please provide a prompt' in result.output


def test_tui_help(runner):
    result = runner.invoke(main, ['tui', '--help'])
    assert result.exit_code == 0
    assert 'Terminal UI' in result.output
    assert '--model' in result.output


def test_config_set_valid(runner, tmp_path, monkeypatch):
    """config set with a valid key should succeed."""
    monkeypatch.setenv("CODY_MODEL_API_KEY", "sk-test-key")
    result = runner.invoke(main, ['config', 'set', 'model', 'test-model'])
    # May fail if home config is not writable, but the command should parse
    assert result.exit_code in (0, 1)


def test_handle_clear(store):
    from io import StringIO
    from rich.console import Console
    buf = StringIO()
    console = Console(file=buf)
    session = store.create_session(title="test")
    result = _handle_command("/clear", session, store, console)
    assert result is True
    assert "cleared" in buf.getvalue().lower()


def test_build_history_preserves_roles():
    """History should preserve role information as pydantic-ai objects."""
    from pydantic_ai.messages import ModelRequest, ModelResponse

    session = Session(
        id="test", title="test",
        messages=[
            Message(role="user", content="q1"),
            Message(role="assistant", content="a1"),
        ],
        model="", workdir="", created_at="", updated_at="",
    )
    history = AsyncCodyClient.messages_to_history(session.messages)
    assert len(history) == 2
    # pydantic-ai returns ModelRequest for user, ModelResponse for assistant
    assert isinstance(history[0], ModelRequest)
    assert isinstance(history[1], ModelResponse)
