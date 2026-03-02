"""Configuration management"""

import json
import os
from pathlib import Path
from typing import Literal, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field


class AuthConfig(BaseModel):
    """Authentication configuration"""
    type: Literal['oauth', 'api_key'] = 'api_key'
    token: Optional[str] = None
    refresh_token: Optional[str] = None
    api_key: Optional[str] = None
    expires_at: Optional[datetime] = None


class SkillConfig(BaseModel):
    """Skill configuration"""
    enabled: list[str] = Field(default_factory=list)
    disabled: list[str] = Field(default_factory=list)


class MCPServerConfig(BaseModel):
    """MCP Server configuration"""
    name: str
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class MCPConfig(BaseModel):
    """MCP configuration"""
    servers: list[MCPServerConfig] = Field(default_factory=list)


class ToolPermissionConfig(BaseModel):
    """Per-tool permission overrides"""
    overrides: dict[str, str] = Field(default_factory=dict)
    default_level: str = "confirm"


class RateLimitConfig(BaseModel):
    """Rate limiting configuration"""
    enabled: bool = False
    max_requests: int = 60
    window_seconds: float = 60.0


class SecurityConfig(BaseModel):
    """Security configuration"""
    allowed_commands: Optional[list[str]] = None
    restricted_paths: list[str] = Field(default_factory=list)
    allowed_roots: list[str] = Field(default_factory=list)
    require_confirmation: bool = True


class Config(BaseModel):
    """Main configuration"""
    model: str = 'anthropic:claude-sonnet-4-0'
    model_base_url: Optional[str] = None
    model_api_key: Optional[str] = None
    claude_oauth_token: Optional[str] = None
    coding_plan_key: Optional[str] = None
    coding_plan_protocol: Literal['openai', 'anthropic'] = 'openai'
    enable_thinking: bool = False
    thinking_budget: Optional[int] = None
    auth: AuthConfig = Field(default_factory=AuthConfig)
    skills: SkillConfig = Field(default_factory=SkillConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    permissions: ToolPermissionConfig = Field(default_factory=ToolPermissionConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)

    @classmethod
    def load(
        cls,
        path: Optional[Union[Path, str]] = None,
        *,
        workdir: Optional[Union[Path, str]] = None,
    ) -> "Config":
        """Load configuration from file.

        *path* — explicit config file; skips discovery.
        *workdir* — required when *path* is omitted; project-local config is
        searched in ``<workdir>/.cody/config.json``.
        """
        if path is None:
            if workdir is None:
                raise TypeError("Config.load() requires workdir when path is not given")
            project_config = Path(workdir) / ".cody" / "config.json"
            global_config = Path.home() / ".cody" / "config.json"

            # Layer: defaults ← global ← project ← env vars
            # This ensures secrets (coding_plan_key, etc.) from the global
            # config survive even when a project config exists but omits them
            # (Config.save() strips secrets for security).
            merged: dict = {}
            if global_config.exists():
                merged.update(json.loads(
                    global_config.read_text(encoding="utf-8"),
                ))
            if project_config.exists():
                merged.update(json.loads(
                    project_config.read_text(encoding="utf-8"),
                ))
            return cls._apply_env_overrides(cls(**merged))

        path = Path(path)
        if not path.exists():
            return cls._apply_env_overrides(cls())

        data = json.loads(path.read_text(encoding="utf-8"))
        return cls._apply_env_overrides(cls(**data))

    @staticmethod
    def _apply_env_overrides(config: "Config") -> "Config":
        """Apply environment variable overrides. Env vars take priority."""
        env_model = os.environ.get("CODY_MODEL")
        if env_model:
            config.model = env_model
        env_base_url = os.environ.get("CODY_MODEL_BASE_URL")
        if env_base_url:
            config.model_base_url = env_base_url
        env_api_key = os.environ.get("CODY_MODEL_API_KEY")
        if env_api_key:
            config.model_api_key = env_api_key
        env_oauth = os.environ.get("CLAUDE_OAUTH_TOKEN")
        if env_oauth:
            config.claude_oauth_token = env_oauth
        env_coding_plan = os.environ.get("CODY_CODING_PLAN_KEY")
        if env_coding_plan:
            config.coding_plan_key = env_coding_plan
        env_coding_plan_proto = os.environ.get("CODY_CODING_PLAN_PROTOCOL")
        if env_coding_plan_proto:
            config.coding_plan_protocol = env_coding_plan_proto
        env_thinking = os.environ.get("CODY_ENABLE_THINKING")
        if env_thinking:
            config.enable_thinking = env_thinking.lower() in ("1", "true", "yes")
        env_thinking_budget = os.environ.get("CODY_THINKING_BUDGET")
        if env_thinking_budget:
            config.thinking_budget = int(env_thinking_budget)
        return config

    def apply_overrides(
        self,
        model: Optional[str] = None,
        model_base_url: Optional[str] = None,
        model_api_key: Optional[str] = None,
        coding_plan_key: Optional[str] = None,
        coding_plan_protocol: Optional[str] = None,
        enable_thinking: Optional[bool] = None,
        thinking_budget: Optional[int] = None,
        claude_oauth_token: Optional[str] = None,
        skills: Optional[list[str]] = None,
        extra_roots: Optional[list[str]] = None,
    ) -> "Config":
        """Apply runtime overrides from CLI flags or request parameters.

        Only non-None values are applied. Returns self for chaining.
        *extra_roots* is additive — entries not already in security.allowed_roots
        are appended; duplicates are silently ignored.
        """
        if model is not None:
            self.model = model
        if model_base_url is not None:
            self.model_base_url = model_base_url
        if model_api_key is not None:
            self.model_api_key = model_api_key
        if coding_plan_key is not None:
            self.coding_plan_key = coding_plan_key
        if coding_plan_protocol is not None:
            self.coding_plan_protocol = coding_plan_protocol
        if enable_thinking is not None:
            self.enable_thinking = enable_thinking
        if thinking_budget is not None:
            self.thinking_budget = thinking_budget
        if claude_oauth_token is not None:
            self.claude_oauth_token = claude_oauth_token
        if skills is not None:
            self.skills.enabled = skills
        if extra_roots:
            existing = set(self.security.allowed_roots)
            for r in extra_roots:
                if r not in existing:
                    self.security.allowed_roots.append(r)
                    existing.add(r)
        return self

    def save(self, path: Union[Path, str]):
        """Save configuration to file.

        Note: model_api_key and claude_oauth_token are excluded from saved
        files for security. Use environment variables instead.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.model_dump(exclude_none=True)
        data.pop("model_api_key", None)
        data.pop("claude_oauth_token", None)
        data.pop("coding_plan_key", None)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
