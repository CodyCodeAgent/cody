"""Tests for configuration management"""

import json
from pathlib import Path

from cody.core.config import (
    AuthConfig,
    Config,
    MCPConfig,
    MCPServerConfig,
    SecurityConfig,
    SkillConfig,
)


# ── Default config ───────────────────────────────────────────────────────────


def test_default_config():
    config = Config()
    assert config.model == "anthropic:claude-sonnet-4-0"
    assert config.auth.type == "api_key"
    assert config.skills.enabled == []
    assert config.skills.disabled == []
    assert config.mcp.servers == []
    assert config.security.allowed_commands is None
    assert config.security.restricted_paths == []
    assert config.security.require_confirmation is True


# ── AuthConfig ───────────────────────────────────────────────────────────────


def test_auth_config_defaults():
    auth = AuthConfig()
    assert auth.type == "api_key"
    assert auth.token is None
    assert auth.api_key is None
    assert auth.refresh_token is None
    assert auth.expires_at is None


def test_auth_config_oauth():
    auth = AuthConfig(type="oauth", token="tok123", refresh_token="ref456")
    assert auth.type == "oauth"
    assert auth.token == "tok123"
    assert auth.refresh_token == "ref456"


# ── SkillConfig ──────────────────────────────────────────────────────────────


def test_skill_config_defaults():
    sc = SkillConfig()
    assert sc.enabled == []
    assert sc.disabled == []


def test_skill_config_with_values():
    sc = SkillConfig(enabled=["git", "docker"], disabled=["web"])
    assert "git" in sc.enabled
    assert "web" in sc.disabled


# ── MCPConfig ────────────────────────────────────────────────────────────────


def test_mcp_config_defaults():
    mcp = MCPConfig()
    assert mcp.servers == []


def test_mcp_server_config():
    server = MCPServerConfig(
        name="github",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_TOKEN": "test"},
    )
    assert server.name == "github"
    assert server.command == "npx"
    assert len(server.args) == 2
    assert server.env["GITHUB_TOKEN"] == "test"


# ── SecurityConfig ───────────────────────────────────────────────────────────


def test_security_config_defaults():
    sec = SecurityConfig()
    assert sec.allowed_commands is None
    assert sec.restricted_paths == []
    assert sec.require_confirmation is True


def test_security_config_with_whitelist():
    sec = SecurityConfig(allowed_commands=["git", "npm"], restricted_paths=["/etc"])
    assert sec.allowed_commands == ["git", "npm"]
    assert sec.restricted_paths == ["/etc"]


# ── Config.load / Config.save ────────────────────────────────────────────────


def test_config_load_nonexistent():
    """Loading from nonexistent path returns defaults"""
    config = Config.load("/tmp/nonexistent_cody_config_12345.json")
    assert config.model == "anthropic:claude-sonnet-4-0"


def test_config_save_and_load(tmp_path):
    """Save config and load it back"""
    config = Config(model="test:model")
    config_path = tmp_path / "config.json"
    config.save(config_path)

    loaded = Config.load(config_path)
    assert loaded.model == "test:model"


def test_config_load_from_json_file(tmp_path):
    """Load config from a manually-written JSON file"""
    data = {
        "model": "openai:gpt-4",
        "skills": {"enabled": ["git"], "disabled": ["docker"]},
        "security": {"allowed_commands": ["git", "ls"]},
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data))

    config = Config.load(config_path)
    assert config.model == "openai:gpt-4"
    assert config.skills.enabled == ["git"]
    assert config.skills.disabled == ["docker"]
    assert config.security.allowed_commands == ["git", "ls"]


def test_config_save_creates_parent_dirs(tmp_path):
    """Save should create parent directories"""
    config = Config()
    config_path = tmp_path / "deep" / "nested" / "config.json"
    config.save(config_path)
    assert config_path.exists()


def test_config_load_default_fallback(tmp_path, monkeypatch):
    """Config.load() with no path falls back to default when no config files exist"""
    # Point cwd and home to empty dirs so no config.json is found
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path / "project")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    (tmp_path / "project").mkdir()
    (tmp_path / "home").mkdir()

    config = Config.load()
    assert config.model == "anthropic:claude-sonnet-4-0"


# ── Config round-trip with nested structures ─────────────────────────────────


def test_config_roundtrip_with_mcp(tmp_path):
    config = Config(
        mcp=MCPConfig(servers=[
            MCPServerConfig(name="test", command="echo", args=["hello"]),
        ])
    )
    config_path = tmp_path / "config.json"
    config.save(config_path)

    loaded = Config.load(config_path)
    assert len(loaded.mcp.servers) == 1
    assert loaded.mcp.servers[0].name == "test"
    assert loaded.mcp.servers[0].command == "echo"
