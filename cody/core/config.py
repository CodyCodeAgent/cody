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
    require_confirmation: bool = True


class Config(BaseModel):
    """Main configuration"""
    model: str = 'anthropic:claude-sonnet-4-0'
    model_base_url: Optional[str] = None
    model_api_key: Optional[str] = None
    auth: AuthConfig = Field(default_factory=AuthConfig)
    skills: SkillConfig = Field(default_factory=SkillConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    permissions: ToolPermissionConfig = Field(default_factory=ToolPermissionConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)

    @classmethod
    def load(cls, path: Optional[Union[Path, str]] = None) -> "Config":
        """Load configuration from file"""
        if path is None:
            # Try project config first, then global
            project_config = Path.cwd() / ".cody" / "config.json"
            global_config = Path.home() / ".cody" / "config.json"
            
            if project_config.exists():
                path = project_config
            elif global_config.exists():
                path = global_config
            else:
                return cls._apply_env_overrides(cls())
        
        path = Path(path)
        if not path.exists():
            return cls._apply_env_overrides(cls())

        data = json.loads(path.read_text())
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
        return config

    def save(self, path: Union[Path, str]):
        """Save configuration to file.

        Note: model_api_key is excluded from saved files for security.
        Use the CODY_MODEL_API_KEY environment variable instead.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.model_dump(exclude_none=True)
        data.pop("model_api_key", None)
        path.write_text(json.dumps(data, indent=2, default=str))
