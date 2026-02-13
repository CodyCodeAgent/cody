"""Tests for tool-level permission system"""

import pytest

from cody.core.permissions import (
    PermissionDeniedError,
    PermissionLevel,
    PermissionManager,
    _DEFAULT_PERMISSIONS,
)


# ── PermissionLevel ─────────────────────────────────────────────────────────


def test_permission_level_values():
    assert PermissionLevel.ALLOW == "allow"
    assert PermissionLevel.DENY == "deny"
    assert PermissionLevel.CONFIRM == "confirm"


def test_permission_level_from_string():
    assert PermissionLevel("allow") == PermissionLevel.ALLOW
    assert PermissionLevel("deny") == PermissionLevel.DENY
    assert PermissionLevel("confirm") == PermissionLevel.CONFIRM


# ── Default permissions ──────────────────────────────────────────────────────


def test_default_read_tools_allowed():
    """Read-only tools should be allowed by default."""
    read_tools = [
        "read_file", "list_directory", "grep", "glob", "search_files",
        "list_skills", "read_skill", "get_agent_status",
        "lsp_diagnostics", "lsp_definition", "lsp_references", "lsp_hover",
        "websearch", "webfetch", "mcp_list_tools", "list_file_changes",
    ]
    for tool in read_tools:
        assert _DEFAULT_PERMISSIONS[tool] == PermissionLevel.ALLOW


def test_default_write_tools_confirm():
    """Mutating tools should require confirmation by default."""
    write_tools = [
        "write_file", "edit_file", "patch", "exec_command",
        "spawn_agent", "kill_agent", "mcp_call",
        "undo_file", "redo_file",
    ]
    for tool in write_tools:
        assert _DEFAULT_PERMISSIONS[tool] == PermissionLevel.CONFIRM


# ── PermissionManager.get_level ──────────────────────────────────────────────


def test_get_level_default():
    pm = PermissionManager()
    assert pm.get_level("read_file") == PermissionLevel.ALLOW
    assert pm.get_level("write_file") == PermissionLevel.CONFIRM


def test_get_level_unknown_tool():
    pm = PermissionManager(default_level=PermissionLevel.CONFIRM)
    assert pm.get_level("unknown_tool") == PermissionLevel.CONFIRM


def test_get_level_override():
    pm = PermissionManager(overrides={"write_file": "allow"})
    assert pm.get_level("write_file") == PermissionLevel.ALLOW


def test_override_beats_default():
    pm = PermissionManager(overrides={"read_file": "deny"})
    assert pm.get_level("read_file") == PermissionLevel.DENY


# ── PermissionManager.check ─────────────────────────────────────────────────


def test_check_allowed():
    pm = PermissionManager()
    result = pm.check("read_file")
    assert result == PermissionLevel.ALLOW


def test_check_confirm():
    pm = PermissionManager()
    result = pm.check("exec_command")
    assert result == PermissionLevel.CONFIRM


def test_check_denied():
    pm = PermissionManager(overrides={"exec_command": "deny"})
    with pytest.raises(PermissionDeniedError) as exc_info:
        pm.check("exec_command")
    assert exc_info.value.tool_name == "exec_command"


# ── PermissionManager.set_override / remove_override ────────────────────────


def test_set_override():
    pm = PermissionManager()
    assert pm.get_level("read_file") == PermissionLevel.ALLOW

    pm.set_override("read_file", PermissionLevel.DENY)
    assert pm.get_level("read_file") == PermissionLevel.DENY


def test_remove_override():
    pm = PermissionManager(overrides={"read_file": "deny"})
    assert pm.get_level("read_file") == PermissionLevel.DENY

    pm.remove_override("read_file")
    assert pm.get_level("read_file") == PermissionLevel.ALLOW


def test_remove_nonexistent_override():
    pm = PermissionManager()
    pm.remove_override("nonexistent")  # should not raise


# ── PermissionManager.list_permissions ───────────────────────────────────────


def test_list_permissions():
    pm = PermissionManager()
    perms = pm.list_permissions()

    assert isinstance(perms, dict)
    assert perms["read_file"] == "allow"
    assert perms["exec_command"] == "confirm"


def test_list_permissions_includes_overrides():
    pm = PermissionManager(overrides={"custom_tool": "allow"})
    perms = pm.list_permissions()

    assert "custom_tool" in perms
    assert perms["custom_tool"] == "allow"


# ── PermissionDeniedError ────────────────────────────────────────────────────


def test_permission_denied_error_message():
    err = PermissionDeniedError("write_file")
    assert "write_file" in str(err)
    assert err.tool_name == "write_file"


def test_permission_denied_error_custom_reason():
    err = PermissionDeniedError("exec_command", reason="Not allowed in sandbox")
    assert str(err) == "Not allowed in sandbox"
    assert err.reason == "Not allowed in sandbox"
