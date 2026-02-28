"""Tests for configuration management"""

import json
from pathlib import Path

import pytest

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
    assert config.model_base_url is None
    assert config.model_api_key is None
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
    """Config.load(workdir=...) falls back to default when no config files exist"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    (tmp_path / "project").mkdir()
    (tmp_path / "home").mkdir()

    config = Config.load(workdir=tmp_path / "project")
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


# ── Custom model provider fields ────────────────────────────────────────────


def test_config_with_custom_model_provider():
    """Config accepts model_base_url and model_api_key"""
    config = Config(
        model="glm-4",
        model_base_url="https://open.bigmodel.cn/api/paas/v4/",
        model_api_key="sk-test-key",
    )
    assert config.model == "glm-4"
    assert config.model_base_url == "https://open.bigmodel.cn/api/paas/v4/"
    assert config.model_api_key == "sk-test-key"


def test_config_load_with_custom_model(tmp_path):
    """Load config with custom model provider from JSON"""
    data = {
        "model": "qwen-coder-plus",
        "model_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data))

    config = Config.load(config_path)
    assert config.model == "qwen-coder-plus"
    assert config.model_base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert config.model_api_key is None


def test_config_save_excludes_api_key(tmp_path):
    """Save should NOT write model_api_key to disk for security"""
    config = Config(
        model="glm-4",
        model_base_url="https://open.bigmodel.cn/api/paas/v4/",
        model_api_key="sk-secret-key",
    )
    config_path = tmp_path / "config.json"
    config.save(config_path)

    saved_data = json.loads(config_path.read_text())
    assert "model_api_key" not in saved_data
    assert saved_data["model"] == "glm-4"
    assert saved_data["model_base_url"] == "https://open.bigmodel.cn/api/paas/v4/"


# ── Environment variable overrides ──────────────────────────────────────────


def test_config_env_overrides_model(tmp_path, monkeypatch):
    """CODY_MODEL env var overrides config file value"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    (tmp_path / "project").mkdir()
    (tmp_path / "home").mkdir()

    monkeypatch.setenv("CODY_MODEL", "glm-4")
    config = Config.load(workdir=tmp_path / "project")
    assert config.model == "glm-4"


def test_config_env_overrides_base_url(tmp_path, monkeypatch):
    """CODY_MODEL_BASE_URL env var overrides config file value"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    (tmp_path / "project").mkdir()
    (tmp_path / "home").mkdir()

    monkeypatch.setenv("CODY_MODEL_BASE_URL", "https://custom.api.com/v1")
    config = Config.load(workdir=tmp_path / "project")
    assert config.model_base_url == "https://custom.api.com/v1"


def test_config_env_overrides_api_key(tmp_path, monkeypatch):
    """CODY_MODEL_API_KEY env var overrides config file value"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    (tmp_path / "project").mkdir()
    (tmp_path / "home").mkdir()

    monkeypatch.setenv("CODY_MODEL_API_KEY", "sk-from-env")
    config = Config.load(workdir=tmp_path / "project")
    assert config.model_api_key == "sk-from-env"


def test_config_env_overrides_file_values(tmp_path, monkeypatch):
    """Env vars take priority over config file values"""
    data = {
        "model": "glm-4",
        "model_base_url": "https://from-file.com/v1",
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data))

    monkeypatch.setenv("CODY_MODEL", "qwen-coder-plus")
    monkeypatch.setenv("CODY_MODEL_BASE_URL", "https://from-env.com/v1")
    monkeypatch.setenv("CODY_MODEL_API_KEY", "sk-env-key")

    config = Config.load(config_path)
    assert config.model == "qwen-coder-plus"
    assert config.model_base_url == "https://from-env.com/v1"
    assert config.model_api_key == "sk-env-key"


# ── Claude OAuth token ──────────────────────────────────────────────────────


def test_config_claude_oauth_token_default():
    """claude_oauth_token defaults to None"""
    config = Config()
    assert config.claude_oauth_token is None


def test_config_claude_oauth_token_set():
    """claude_oauth_token can be set directly"""
    config = Config(claude_oauth_token="oauth-tok-123")
    assert config.claude_oauth_token == "oauth-tok-123"


def test_config_env_overrides_claude_oauth_token(tmp_path, monkeypatch):
    """CLAUDE_OAUTH_TOKEN env var overrides config"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    (tmp_path / "project").mkdir()
    (tmp_path / "home").mkdir()

    monkeypatch.setenv("CLAUDE_OAUTH_TOKEN", "oauth-from-env")
    config = Config.load(workdir=tmp_path / "project")
    assert config.claude_oauth_token == "oauth-from-env"


def test_config_save_excludes_oauth_token(tmp_path):
    """Save should NOT write claude_oauth_token to disk for security"""
    config = Config(claude_oauth_token="oauth-secret")
    config_path = tmp_path / "config.json"
    config.save(config_path)

    saved_data = json.loads(config_path.read_text())
    assert "claude_oauth_token" not in saved_data


# ── Coding Plan ──────────────────────────────────────────────────────────────


def test_config_coding_plan_key_default():
    """coding_plan_key defaults to None"""
    config = Config()
    assert config.coding_plan_key is None
    assert config.coding_plan_protocol == "openai"


def test_config_coding_plan_key_set():
    """coding_plan_key can be set directly"""
    config = Config(coding_plan_key="sk-sp-test123")
    assert config.coding_plan_key == "sk-sp-test123"


def test_config_coding_plan_protocol_anthropic():
    """coding_plan_protocol can be set to anthropic"""
    config = Config(coding_plan_protocol="anthropic")
    assert config.coding_plan_protocol == "anthropic"


def test_config_env_overrides_coding_plan_key(tmp_path, monkeypatch):
    """CODY_CODING_PLAN_KEY env var overrides config"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    (tmp_path / "project").mkdir()
    (tmp_path / "home").mkdir()

    monkeypatch.setenv("CODY_CODING_PLAN_KEY", "sk-sp-from-env")
    config = Config.load(workdir=tmp_path / "project")
    assert config.coding_plan_key == "sk-sp-from-env"


def test_config_env_overrides_coding_plan_protocol(tmp_path, monkeypatch):
    """CODY_CODING_PLAN_PROTOCOL env var overrides config"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    (tmp_path / "project").mkdir()
    (tmp_path / "home").mkdir()

    monkeypatch.setenv("CODY_CODING_PLAN_PROTOCOL", "anthropic")
    config = Config.load(workdir=tmp_path / "project")
    assert config.coding_plan_protocol == "anthropic"


def test_config_save_excludes_coding_plan_key(tmp_path):
    """Save should NOT write coding_plan_key to disk for security"""
    config = Config(coding_plan_key="sk-sp-secret")
    config_path = tmp_path / "config.json"
    config.save(config_path)

    saved_data = json.loads(config_path.read_text())
    assert "coding_plan_key" not in saved_data


def test_config_coding_plan_from_json(tmp_path):
    """Load config with coding_plan_protocol from JSON"""
    data = {
        "model": "qwen3.5",
        "coding_plan_protocol": "anthropic",
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data))

    config = Config.load(config_path)
    assert config.model == "qwen3.5"
    assert config.coding_plan_protocol == "anthropic"


# ── Config.load with workdir ────────────────────────────────────────────────


def test_config_load_workdir_finds_project_config(tmp_path, monkeypatch):
    """Config.load(workdir=X) looks for .cody/config.json in X, not cwd."""
    # Put a project config in a different directory than cwd
    project_dir = tmp_path / "my-project"
    (project_dir / ".cody").mkdir(parents=True)
    (project_dir / ".cody" / "config.json").write_text(
        json.dumps({"model": "project-model"})
    )

    # cwd has no config
    cwd_dir = tmp_path / "elsewhere"
    cwd_dir.mkdir()
    monkeypatch.setattr(Path, "cwd", lambda: cwd_dir)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "nohome")
    (tmp_path / "nohome").mkdir()

    config = Config.load(workdir=project_dir)
    assert config.model == "project-model"


def test_config_load_requires_workdir_when_no_path():
    """Config.load() without path or workdir raises TypeError."""
    with pytest.raises(TypeError, match="requires workdir"):
        Config.load()


def test_config_load_workdir_no_project_config_falls_to_global(tmp_path, monkeypatch):
    """When workdir has no .cody/config.json, global config is tried."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    home_dir = tmp_path / "home"
    (home_dir / ".cody").mkdir(parents=True)
    (home_dir / ".cody" / "config.json").write_text(
        json.dumps({"model": "global-model"})
    )

    monkeypatch.setattr(Path, "home", lambda: home_dir)

    config = Config.load(workdir=project_dir)
    assert config.model == "global-model"
