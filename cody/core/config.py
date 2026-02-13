"""Configuration management"""

import json
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
                return cls()
        
        path = Path(path)
        if not path.exists():
            return cls()
        
        data = json.loads(path.read_text())
        return cls(**data)
    
    def save(self, path: Union[Path, str]):
        """Save configuration to file"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2))
