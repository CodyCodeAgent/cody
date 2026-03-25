"""Tests for tool output truncation."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cody.core.config import Config, TruncationConfig
from cody.core.tools.truncate import truncate_output


# ── truncate_output ───────────────────────────────────────────────────────


def test_short_output_unchanged():
    """Output under the limit passes through unmodified."""
    result = truncate_output("hello world", "grep", max_chars=1000)
    assert result == "hello world"


def test_exact_limit_unchanged():
    """Output exactly at the limit is not truncated."""
    text = "x" * 100
    result = truncate_output(text, "grep", max_chars=100)
    assert result == text


def test_over_limit_truncated(tmp_path):
    """Output over the limit is truncated with trailer."""
    text = "a" * 200
    result = truncate_output(text, "grep", max_chars=50, workdir=tmp_path)
    assert result.startswith("a" * 50)
    assert "OUTPUT TRUNCATED" in result
    assert "200 chars total" in result
    assert "showing first 50" in result


def test_truncated_saves_temp_file(tmp_path):
    """Full output is saved to a temp file."""
    text = "line\n" * 100
    result = truncate_output(text, "test_tool", max_chars=50, workdir=tmp_path)
    assert "Full output saved to:" in result
    assert "read_file(" in result

    # Extract path and verify content.
    for line in result.split("\n"):
        if "Full output saved to:" in line:
            path = line.split("Full output saved to:")[1].strip()
            saved = Path(path).read_text()
            assert saved == text
            break
    else:
        pytest.fail("No temp file path found in truncated output")


def test_truncated_no_workdir():
    """Truncation works even without workdir (uses system temp)."""
    text = "b" * 200
    result = truncate_output(text, "cmd", max_chars=50)
    assert "OUTPUT TRUNCATED" in result
    assert "Full output saved to:" in result


def test_empty_output():
    result = truncate_output("", "grep", max_chars=100)
    assert result == ""


def test_tool_name_in_suffix(tmp_path):
    """The tool name appears in the temp file suffix."""
    text = "x" * 200
    result = truncate_output(text, "exec_command", max_chars=50, workdir=tmp_path)
    for line in result.split("\n"):
        if "Full output saved to:" in line:
            path = line.split("Full output saved to:")[1].strip()
            assert "exec_command" in path
            break


# ── TruncationConfig ─────────────────────────────────────────────────────


def test_truncation_config_defaults():
    cfg = Config()
    assert cfg.truncation.enabled is True
    assert cfg.truncation.max_output_chars == 120_000


def test_truncation_config_custom():
    cfg = Config(truncation=TruncationConfig(enabled=False, max_output_chars=50_000))
    assert cfg.truncation.enabled is False
    assert cfg.truncation.max_output_chars == 50_000


# ── _maybe_truncate integration ──────────────────────────────────────────


def test_maybe_truncate_applies(tmp_path):
    """_maybe_truncate uses config from RunContext deps."""
    from cody.core.tools._base import _maybe_truncate

    # Build a mock ctx with deps.config.truncation
    cfg = Config(truncation=TruncationConfig(enabled=True, max_output_chars=50))
    deps = MagicMock()
    deps.config = cfg
    deps.workdir = tmp_path
    ctx = MagicMock()
    ctx.deps = deps

    text = "x" * 200
    result = _maybe_truncate(text, "grep", (ctx,), {})
    assert "OUTPUT TRUNCATED" in result


def test_maybe_truncate_disabled():
    """Truncation disabled → passthrough."""
    from cody.core.tools._base import _maybe_truncate

    cfg = Config(truncation=TruncationConfig(enabled=False))
    deps = MagicMock()
    deps.config = cfg
    ctx = MagicMock()
    ctx.deps = deps

    text = "x" * 999_999
    result = _maybe_truncate(text, "grep", (ctx,), {})
    assert result == text


def test_maybe_truncate_no_ctx():
    """No ctx → passthrough."""
    from cody.core.tools._base import _maybe_truncate

    text = "x" * 200
    result = _maybe_truncate(text, "grep", (), {})
    assert result == text


def test_maybe_truncate_short_output():
    """Short output → passthrough even with truncation enabled."""
    from cody.core.tools._base import _maybe_truncate

    cfg = Config(truncation=TruncationConfig(enabled=True, max_output_chars=1000))
    deps = MagicMock()
    deps.config = cfg
    deps.workdir = None
    ctx = MagicMock()
    ctx.deps = deps

    result = _maybe_truncate("short", "grep", (ctx,), {})
    assert result == "short"
