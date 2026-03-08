"""Tests for web/backend/helpers.py — resolve_chat_runner()."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from web.backend.helpers import resolve_chat_runner


@pytest.fixture
def workdir(tmp_path):
    """Create a workdir with a minimal config."""
    cody_dir = tmp_path / ".cody"
    cody_dir.mkdir()
    (cody_dir / "config.json").write_text("{}")
    return tmp_path


# ── resolve_chat_runner ──────────────────────────────────────────────────────


def test_resolve_chat_runner_no_api_key(workdir):
    """Raises ValueError when no API key is configured."""
    with patch("web.backend.helpers.get_config") as mock_config:
        cfg = MagicMock()
        cfg.is_ready.return_value = False
        mock_config.return_value = cfg

        with pytest.raises(ValueError, match="No API key"):
            resolve_chat_runner(workdir, {})


def test_resolve_chat_runner_api_key_in_data(workdir):
    """Does not raise when API key is in data dict, even if config not ready."""
    with patch("web.backend.helpers.get_config") as mock_config, \
         patch("web.backend.helpers.AgentRunner") as MockRunner:
        cfg = MagicMock()
        cfg.is_ready.return_value = False
        mock_config.return_value = cfg

        data = {"model_api_key": "sk-test-123"}
        config, runner = resolve_chat_runner(workdir, data)

        cfg.apply_overrides.assert_called_once()
        MockRunner.assert_called_once()


def test_resolve_chat_runner_cached_runner(workdir):
    """Uses cached runner when no overrides and no extra roots."""
    with patch("web.backend.helpers.get_config") as mock_config, \
         patch("web.backend.helpers.get_runner") as mock_get_runner:
        cfg = MagicMock()
        cfg.is_ready.return_value = True
        mock_config.return_value = cfg
        mock_runner = MagicMock()
        mock_get_runner.return_value = mock_runner

        config, runner = resolve_chat_runner(workdir, {})

        assert runner is mock_runner
        mock_get_runner.assert_called_once_with(workdir)
        cfg.apply_overrides.assert_not_called()


def test_resolve_chat_runner_with_overrides(workdir):
    """Creates new runner when overrides are present."""
    with patch("web.backend.helpers.get_config") as mock_config, \
         patch("web.backend.helpers.AgentRunner") as MockRunner:
        cfg = MagicMock()
        cfg.is_ready.return_value = True
        mock_config.return_value = cfg

        data = {"model": "gpt-4o", "enable_thinking": True}
        config, runner = resolve_chat_runner(workdir, data)

        cfg.apply_overrides.assert_called_once_with(
            model="gpt-4o",
            model_base_url=None,
            model_api_key=None,
            enable_thinking=True,
            thinking_budget=None,
        )
        MockRunner.assert_called_once()


def test_resolve_chat_runner_with_code_paths(workdir):
    """Creates new runner when code_paths (extra_roots) are present."""
    with patch("web.backend.helpers.get_config") as mock_config, \
         patch("web.backend.helpers.AgentRunner") as MockRunner:
        cfg = MagicMock()
        cfg.is_ready.return_value = True
        mock_config.return_value = cfg

        config, runner = resolve_chat_runner(
            workdir, {}, code_paths=["/tmp/other"],
        )

        MockRunner.assert_called_once()
        call_kwargs = MockRunner.call_args[1]
        assert call_kwargs["extra_roots"] == [Path("/tmp/other")]
        cfg.apply_overrides.assert_not_called()


def test_resolve_chat_runner_empty_code_paths(workdir):
    """Empty code_paths should use cached runner."""
    with patch("web.backend.helpers.get_config") as mock_config, \
         patch("web.backend.helpers.get_runner") as mock_get_runner:
        cfg = MagicMock()
        cfg.is_ready.return_value = True
        mock_config.return_value = cfg
        mock_get_runner.return_value = MagicMock()

        config, runner = resolve_chat_runner(workdir, {}, code_paths=[])

        mock_get_runner.assert_called_once_with(workdir)
