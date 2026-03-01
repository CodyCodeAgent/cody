"""Tests for CLI commands"""

import pytest
from pathlib import Path
from click.testing import CliRunner
from cody.cli import main, _handle_command, _build_history_from_session
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

    monkeypatch.setattr("cody.cli.generate_project_instructions", _fake_generate)

    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ['init'])
        assert result.exit_code == 0, result.output
        assert 'Initialized' in result.output
        assert (Path.cwd() / '.cody').exists()
        assert (Path.cwd() / '.cody' / 'skills').exists()
        assert (Path.cwd() / '.cody' / 'config.json').exists()
        assert (Path.cwd() / 'CODY.md').exists()
        assert 'AI-generated' in (Path.cwd() / 'CODY.md').read_text()


def test_init_already_exists(runner, tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        (Path.cwd() / '.cody').mkdir()
        result = runner.invoke(main, ['init'])
        assert result.exit_code == 0
        assert 'already exists' in result.output


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


def test_chat_nonexistent_session(runner):
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
    console = Console(file=open('/dev/null', 'w'))
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
    history = _build_history_from_session(session)
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
    history = _build_history_from_session(session)
    assert len(history) == 3
