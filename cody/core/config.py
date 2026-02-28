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
    claude_oauth_token: Optional[str] = None
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
        env_oauth = os.environ.get("CLAUDE_OAUTH_TOKEN")
        if env_oauth:
            config.claude_oauth_token = env_oauth
        return config

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
        path.write_text(json.dumps(data, indent=2, default=str))

    def resolve_model(self):
        """Resolve model to a Pydantic AI model instance.

        Priority:
        1. model_base_url → OpenAIProvider (OpenAI-compatible APIs)
        2. claude_oauth_token → AnthropicProvider with OAuth auth_token
        3. Default → model string for Pydantic AI's built-in routing
           (uses ANTHROPIC_API_KEY env var for Anthropic models)
        """
        if self.model_base_url:
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider

            provider = OpenAIProvider(
                base_url=self.model_base_url,
                api_key=self.model_api_key or "not-set",
            )
            return OpenAIChatModel(self.model, provider=provider)

        if self.claude_oauth_token:
            from anthropic import AsyncAnthropic
            from pydantic_ai.models.anthropic import AnthropicModel
            from pydantic_ai.providers.anthropic import AnthropicProvider

            client = AsyncAnthropic(auth_token=self.claude_oauth_token)
            provider = AnthropicProvider(anthropic_client=client)
            # Strip "anthropic:" prefix if present for AnthropicModel
            model_name = self.model
            if model_name.startswith("anthropic:"):
                model_name = model_name[len("anthropic:"):]
            return AnthropicModel(model_name, provider=provider)

        return self.model
