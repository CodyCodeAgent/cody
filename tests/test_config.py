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
    assert config.security.allowed_roots == []
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


def test_config_save_includes_api_key(tmp_path):
    """Save should persist model_api_key to disk"""
    config = Config(
        model="glm-4",
        model_base_url="https://open.bigmodel.cn/api/paas/v4/",
        model_api_key="sk-secret-key",
    )
    config_path = tmp_path / "config.json"
    config.save(config_path)

    saved_data = json.loads(config_path.read_text())
    assert saved_data["model_api_key"] == "sk-secret-key"
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


# ── Config.is_ready / Config.missing_fields ──────────────────────────────


def test_config_is_ready_with_api_key():
    """Config with model_api_key (no base_url) is ready"""
    config = Config(model_api_key="sk-test")
    assert config.is_ready() is True


def test_config_is_ready_with_base_url_and_key():
    """Config with base_url + api_key is ready"""
    config = Config(model_base_url="https://api.example.com/v1", model_api_key="sk-test")
    assert config.is_ready() is True


def test_config_not_ready_with_base_url_no_key():
    """Config with base_url but no api_key is NOT ready"""
    config = Config(model_base_url="https://api.example.com/v1")
    assert config.is_ready() is False


def test_config_not_ready_no_key():
    """Config with no api_key is NOT ready"""
    config = Config()
    assert config.is_ready() is False


def test_config_missing_fields_no_key():
    """missing_fields reports missing api_key when not configured"""
    config = Config()
    missing = config.missing_fields()
    assert len(missing) == 1
    assert "model_api_key" in missing[0]


def test_config_missing_fields_empty_when_ready():
    """missing_fields returns empty list when config is ready"""
    config = Config(model_api_key="sk-test")
    assert config.missing_fields() == []


def test_config_load_strips_legacy_oauth(tmp_path):
    """Config.load ignores legacy claude_oauth_token in JSON files"""
    data = {"model": "anthropic:claude-sonnet-4-0", "claude_oauth_token": "old-oauth-token"}
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data))

    config = Config.load(config_path)
    assert config.model == "anthropic:claude-sonnet-4-0"
    assert not hasattr(config, "claude_oauth_token") or getattr(config, "claude_oauth_token", None) is None


# ── Legacy CODY_CODING_PLAN_KEY env var compat ───────────────────────────────


def test_config_env_coding_plan_key_maps_to_model_api_key(tmp_path, monkeypatch):
    """CODY_CODING_PLAN_KEY env var maps to model_api_key"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    (tmp_path / "project").mkdir()
    (tmp_path / "home").mkdir()

    monkeypatch.setenv("CODY_CODING_PLAN_KEY", "sk-sp-from-env")
    config = Config.load(workdir=tmp_path / "project")
    assert config.model_api_key == "sk-sp-from-env"


def test_config_env_coding_plan_key_does_not_override_model_api_key(tmp_path, monkeypatch):
    """CODY_CODING_PLAN_KEY does NOT override explicit CODY_MODEL_API_KEY"""
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    (tmp_path / "project").mkdir()
    (tmp_path / "home").mkdir()

    monkeypatch.setenv("CODY_MODEL_API_KEY", "sk-explicit")
    monkeypatch.setenv("CODY_CODING_PLAN_KEY", "sk-sp-from-env")
    config = Config.load(workdir=tmp_path / "project")
    assert config.model_api_key == "sk-explicit"


def test_config_load_strips_legacy_coding_plan_fields(tmp_path):
    """Config.load ignores legacy coding_plan fields in JSON files"""
    data = {"model": "qwen3.5", "coding_plan_key": "sk-sp-old", "coding_plan_protocol": "anthropic"}
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data))

    config = Config.load(config_path)
    assert config.model == "qwen3.5"
    assert not hasattr(config, "coding_plan_key") or getattr(config, "coding_plan_key", None) is None


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


# ── SecurityConfig.allowed_roots ─────────────────────────────────────────────


def test_security_config_allowed_roots_default():
    sec = SecurityConfig()
    assert sec.allowed_roots == []


def test_security_config_allowed_roots_from_json(tmp_path):
    data = {"security": {"allowed_roots": ["/tmp/shared", "/data/models"]}}
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data))
    config = Config.load(config_path)
    assert config.security.allowed_roots == ["/tmp/shared", "/data/models"]


def test_apply_overrides_extra_roots_additive():
    config = Config()
    config.security.allowed_roots = ["/existing/root"]
    config.apply_overrides(extra_roots=["/new/root"])
    assert "/existing/root" in config.security.allowed_roots
    assert "/new/root" in config.security.allowed_roots
    assert len(config.security.allowed_roots) == 2


def test_apply_overrides_extra_roots_no_duplicates():
    config = Config()
    config.security.allowed_roots = ["/some/root"]
    config.apply_overrides(extra_roots=["/some/root"])
    assert config.security.allowed_roots.count("/some/root") == 1


def test_apply_overrides_extra_roots_none_is_noop():
    config = Config()
    config.security.allowed_roots = ["/a"]
    config.apply_overrides(extra_roots=None)
    assert config.security.allowed_roots == ["/a"]


def test_apply_overrides_extra_roots_empty_is_noop():
    config = Config()
    config.security.allowed_roots = ["/a"]
    config.apply_overrides(extra_roots=[])
    assert config.security.allowed_roots == ["/a"]
