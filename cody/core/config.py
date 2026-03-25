"""Configuration management"""

import json
import logging
import os
from pathlib import Path
from typing import Literal, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, preserving nested dict keys."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


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
    custom_dirs: list[str] = Field(default_factory=list)


class MCPServerConfig(BaseModel):
    """MCP Server configuration.

    Supports two transport modes:
    - stdio (default): launches a subprocess, communicates via stdin/stdout JSON-RPC.
      Requires ``command`` (and optionally ``args``, ``env``).
    - http: sends JSON-RPC requests over HTTP POST.
      Requires ``url`` (and optionally ``headers``).
    """
    name: str
    transport: Literal['stdio', 'http'] = 'stdio'
    # stdio transport fields
    command: str = ''
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    # http transport fields
    url: str = ''
    headers: dict[str, str] = Field(default_factory=dict)


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
    blocked_commands: list[str] = Field(default_factory=list)
    restricted_paths: list[str] = Field(default_factory=list)
    allowed_roots: list[str] = Field(default_factory=list)
    strict_read_boundary: bool = False
    require_confirmation: bool = True
    allow_private_urls: bool = False
    command_timeout: int = 30


class CompactionConfig(BaseModel):
    """Context compaction configuration."""
    use_llm: bool = False
    model: Optional[str] = None
    model_base_url: Optional[str] = None
    model_api_key: Optional[str] = None
    max_tokens: int = 100_000
    # Percentage-based trigger: when set > 0, max_tokens is computed as
    # trigger_ratio × context_window_tokens.  Overrides max_tokens.
    trigger_ratio: float = 0.0
    context_window_tokens: int = 0
    keep_recent: int = 4
    # Token-based recent preservation: when > 0, overrides keep_recent
    # (count-based) with a token budget for the recent messages window.
    keep_recent_tokens: int = 0
    max_summary_tokens: int = 500
    # Selective pruning — try to free tokens by replacing old tool outputs
    # with lightweight markers before resorting to full compaction.
    enable_pruning: bool = True
    prune_protect_tokens: int = 40_000
    prune_min_saving_tokens: int = 20_000
    prune_min_content_tokens: int = 200

    def effective_max_tokens(self) -> int:
        """Compute the effective max_tokens threshold.

        If ``trigger_ratio`` and ``context_window_tokens`` are both set,
        returns ``int(trigger_ratio * context_window_tokens)``.
        Otherwise returns ``max_tokens``.
        """
        if self.trigger_ratio > 0 and self.context_window_tokens > 0:
            return int(self.trigger_ratio * self.context_window_tokens)
        return self.max_tokens


class InteractionConfig(BaseModel):
    """Human-in-the-loop interaction configuration."""
    enabled: bool = False
    timeout: float = 30.0  # seconds; 0 = no timeout (wait forever)

class TruncationConfig(BaseModel):
    """Tool output truncation configuration."""
    enabled: bool = True
    max_output_chars: int = 120_000  # ~30K tokens

class RetryConfig(BaseModel):
    """LLM API retry configuration with exponential backoff."""
    enabled: bool = True
    max_retries: int = 3
    base_delay: float = 2.0
    max_delay: float = 30.0


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration for automatic run termination."""
    enabled: bool = True
    max_tokens: int = 200_000
    max_cost_usd: float = 5.0
    loop_detect_turns: int = 6
    loop_similarity_threshold: float = 0.9
    model_prices: dict[str, float] = Field(default_factory=lambda: {
        "default": 0.000003,  # USD per token fallback
    })


class Config(BaseModel):
    """Main configuration"""
    model: str = ''
    model_base_url: Optional[str] = None
    model_api_key: Optional[str] = None
    enable_thinking: bool = False
    thinking_budget: Optional[int] = None
    auth: AuthConfig = Field(default_factory=AuthConfig)
    skills: SkillConfig = Field(default_factory=SkillConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    permissions: ToolPermissionConfig = Field(default_factory=ToolPermissionConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    truncation: TruncationConfig = Field(default_factory=TruncationConfig)
    compaction: CompactionConfig = Field(default_factory=CompactionConfig)
    interaction: InteractionConfig = Field(default_factory=InteractionConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)

    def is_ready(self) -> bool:
        """Check if configuration has enough info to make API calls."""
        return bool(self.model and self.model_base_url)

    def missing_fields(self) -> list:
        """Return descriptions of missing configuration fields."""
        missing = []
        if not self.model:
            missing.append("model (run 'cody config setup' to configure)")
        if not self.model_base_url:
            missing.append("model_base_url (run 'cody config setup' to configure)")
        return missing

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
                workdir = Path.cwd()
            project_config = Path(workdir) / ".cody" / "config.json"
            global_config = Path.home() / ".cody" / "config.json"

            # Layer: defaults ← global ← project ← env vars
            merged: dict = {}
            if global_config.exists():
                try:
                    merged = _deep_merge(merged, json.loads(
                        global_config.read_text(encoding="utf-8"),
                    ))
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning("Failed to parse %s: %s, skipping", global_config, e)
            if project_config.exists():
                try:
                    merged = _deep_merge(merged, json.loads(
                        project_config.read_text(encoding="utf-8"),
                    ))
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning("Failed to parse %s: %s, skipping", project_config, e)
            # Strip legacy fields from old config files
            merged.pop("coding_plan_key", None)
            merged.pop("coding_plan_protocol", None)
            merged.pop("claude_oauth_token", None)
            return cls._apply_env_overrides(cls(**merged))

        path = Path(path)
        if not path.exists():
            return cls._apply_env_overrides(cls())

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to parse %s: %s, using defaults", path, e)
            return cls._apply_env_overrides(cls())
        # Strip legacy fields from old config files
        data.pop("coding_plan_key", None)
        data.pop("coding_plan_protocol", None)
        data.pop("claude_oauth_token", None)
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
        # Legacy: CODY_CODING_PLAN_KEY maps to model_api_key
        env_coding_plan = os.environ.get("CODY_CODING_PLAN_KEY")
        if env_coding_plan and not config.model_api_key:
            config.model_api_key = env_coding_plan
        env_thinking = os.environ.get("CODY_ENABLE_THINKING")
        if env_thinking:
            config.enable_thinking = env_thinking.lower() in ("1", "true", "yes")
        env_thinking_budget = os.environ.get("CODY_THINKING_BUDGET")
        if env_thinking_budget:
            try:
                config.thinking_budget = int(env_thinking_budget)
            except ValueError:
                logger.warning(
                    "Invalid CODY_THINKING_BUDGET value: %r, ignoring",
                    env_thinking_budget,
                )
        env_compaction_llm = os.environ.get("CODY_COMPACTION_USE_LLM")
        if env_compaction_llm:
            config.compaction.use_llm = env_compaction_llm.lower() in (
                "1", "true", "yes",
            )
        env_compaction_model = os.environ.get("CODY_COMPACTION_MODEL")
        if env_compaction_model:
            config.compaction.model = env_compaction_model
        env_skill_dirs = os.environ.get("CODY_SKILL_DIRS")
        if env_skill_dirs:
            config.skills.custom_dirs = [
                d.strip() for d in env_skill_dirs.split(":") if d.strip()
            ]
        return config

    def apply_overrides(
        self,
        model: Optional[str] = None,
        model_base_url: Optional[str] = None,
        model_api_key: Optional[str] = None,
        enable_thinking: Optional[bool] = None,
        thinking_budget: Optional[int] = None,
        skills: Optional[list[str]] = None,
        skill_dirs: Optional[list[str]] = None,
        extra_roots: Optional[list[str]] = None,
    ) -> "Config":
        """Apply runtime overrides from CLI flags or request parameters.

        Only non-None values are applied. Returns self for chaining.
        *extra_roots* is additive — entries not already in security.allowed_roots
        are appended; duplicates are silently ignored.
        *skill_dirs* is additive — entries not already in skills.custom_dirs
        are appended; duplicates are silently ignored.
        """
        if model is not None:
            self.model = model
        if model_base_url is not None:
            self.model_base_url = model_base_url
        if model_api_key is not None:
            self.model_api_key = model_api_key
        if enable_thinking is not None:
            self.enable_thinking = enable_thinking
        if thinking_budget is not None:
            self.thinking_budget = thinking_budget
        if skills is not None:
            self.skills.enabled = skills
        if skill_dirs:
            existing = set(self.skills.custom_dirs)
            for d in skill_dirs:
                if d not in existing:
                    self.skills.custom_dirs.append(d)
                    existing.add(d)
        if extra_roots:
            existing = set(self.security.allowed_roots)
            for r in extra_roots:
                if r not in existing:
                    self.security.allowed_roots.append(r)
                    existing.add(r)
        return self

    def save(self, path: Union[Path, str]):
        """Save configuration to file.

        Sensitive fields (API keys, tokens) are excluded from persistence.
        Use environment variables (CODY_MODEL_API_KEY) to supply secrets.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.model_dump(exclude_none=True)
        # Exclude sensitive fields from persistence
        data.pop("model_api_key", None)
        if "compaction" in data:
            data["compaction"].pop("model_api_key", None)
        if "auth" in data:
            data["auth"].pop("token", None)
            data["auth"].pop("refresh_token", None)
            data["auth"].pop("api_key", None)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        # Restrict file permissions (owner read/write only)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
