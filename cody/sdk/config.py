"""Cody SDK - Configuration management.

Provides a clean configuration interface for SDK clients.
"""

from dataclasses import dataclass, field
from typing import Optional, Literal


@dataclass
class ModelConfig:
    """Model configuration."""
    
    model: str = ""
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    provider: Optional[str] = None
    
    # Model-specific settings
    enable_thinking: bool = False
    thinking_budget: Optional[int] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for core config."""
        result = {"model": self.model}
        if self.base_url:
            result["model_base_url"] = self.base_url
        if self.api_key:
            result["model_api_key"] = self.api_key
        return result


@dataclass
class PermissionConfig:
    """Permission configuration for tools."""
    
    default_level: Literal["allow", "deny", "confirm"] = "confirm"
    overrides: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for core config."""
        return {
            "default_level": self.default_level,
            "overrides": self.overrides,
        }


@dataclass
class SecurityConfig:
    """Security configuration."""
    
    allowed_roots: list[str] = field(default_factory=list)
    blocked_commands: list[str] = field(default_factory=list)
    strict_read_boundary: bool = False
    enable_audit: bool = True
    audit_path: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for core config."""
        return {
            "allowed_roots": self.allowed_roots,
            "blocked_commands": self.blocked_commands,
            "strict_read_boundary": self.strict_read_boundary,
            "enable_audit": self.enable_audit,
            "audit_path": self.audit_path,
        }


@dataclass
class MCPServerConfig:
    """Single MCP server configuration.

    For stdio transport (default):
        MCPServerConfig(name="github", command="npx",
                        args=["-y", "@modelcontextprotocol/server-github"],
                        env={"GITHUB_TOKEN": "..."})

    For HTTP transport:
        MCPServerConfig(name="feishu", transport="http",
                        url="https://mcp.feishu.cn/mcp",
                        headers={"X-Lark-MCP-UAT": "..."})
    """

    name: str = ""
    transport: Literal['stdio', 'http'] = 'stdio'
    # stdio fields
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    # http fields
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for core config."""
        d: dict = {"name": self.name, "transport": self.transport}
        if self.transport == 'stdio':
            d["command"] = self.command
            if self.args:
                d["args"] = self.args
            if self.env:
                d["env"] = self.env
        else:
            d["url"] = self.url
            if self.headers:
                d["headers"] = self.headers
        return d


@dataclass
class MCPConfig:
    """MCP server configuration."""

    servers: list[MCPServerConfig | dict] = field(default_factory=list)
    enabled: bool = True

    def to_dict(self) -> dict:
        """Convert to dictionary for core config."""
        if not self.enabled:
            return {"servers": []}
        result = []
        for s in self.servers:
            if isinstance(s, MCPServerConfig):
                result.append(s.to_dict())
            else:
                result.append(s)
        return {"servers": result}


@dataclass
class InteractionConfig:
    """Human-in-the-loop interaction configuration.

    When enabled, the runner pauses on interaction requests and waits
    for a human response via ``submit_interaction()``.  When disabled
    (default), interaction requests are auto-approved so the AI runs
    autonomously.

    Only effective with async clients (``run()`` / ``stream()``).
    ``run_sync()`` always auto-approves regardless of this setting.
    """

    enabled: bool = False
    timeout: float = 30.0  # seconds; 0 = no timeout

    def to_dict(self) -> dict:
        """Convert to dictionary for core config."""
        return {
            "enabled": self.enabled,
            "timeout": self.timeout,
        }


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration for automatic run termination.

    Controls safety limits that prevent runaway token usage and cost.
    """

    enabled: bool = True
    max_tokens: int = 200_000
    max_cost_usd: float = 5.0
    max_steps: int = 0  # Max tool call steps per run; 0 = unlimited
    loop_detect_turns: int = 6
    loop_similarity_threshold: float = 0.9
    model_prices: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for core config."""
        d: dict = {
            "enabled": self.enabled,
            "max_tokens": self.max_tokens,
            "max_cost_usd": self.max_cost_usd,
            "max_steps": self.max_steps,
            "loop_detect_turns": self.loop_detect_turns,
            "loop_similarity_threshold": self.loop_similarity_threshold,
        }
        if self.model_prices:
            d["model_prices"] = self.model_prices
        return d


@dataclass
class LSPConfig:
    """LSP configuration."""
    
    enabled: bool = True
    languages: list[str] = field(default_factory=lambda: ["python", "typescript", "go"])
    
    def to_dict(self) -> dict:
        """Convert to dictionary for core config."""
        return {
            "enabled": self.enabled,
            "languages": self.languages,
        }


@dataclass
class SDKConfig:
    """Complete SDK configuration.
    
    Usage:
        config = SDKConfig(
            model="your-model-name",
            workdir="/path/to/project",
            enable_thinking=True,
            permissions={"exec_command": "allow"},
        )
        
        async with AsyncCodyClient(config=config) as client:
            result = await client.run("task")
    """
    
    # Working directory
    workdir: Optional[str] = None
    
    # Model configuration
    model: ModelConfig = field(default_factory=ModelConfig)
    
    # Session database path
    db_path: Optional[str] = None
    
    # Permissions
    permissions: PermissionConfig = field(default_factory=PermissionConfig)
    
    # Security
    security: SecurityConfig = field(default_factory=SecurityConfig)
    
    # MCP
    mcp: MCPConfig = field(default_factory=MCPConfig)
    
    # LSP
    lsp: LSPConfig = field(default_factory=LSPConfig)
    
    # Interaction (human-in-the-loop)
    interaction: InteractionConfig = field(default_factory=InteractionConfig)

    # Circuit breaker
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)

    # Custom skill directories
    skill_dirs: list[str] = field(default_factory=list)

    # Metrics & monitoring
    enable_metrics: bool = False
    enable_events: bool = False
    
    @classmethod
    def from_dict(cls, data: dict) -> "SDKConfig":
        """Create SDKConfig from dictionary."""
        config = cls()
        
        if "workdir" in data:
            config.workdir = data["workdir"]
        if "db_path" in data:
            config.db_path = data["db_path"]
        
        if "model" in data:
            model_data = data["model"]
            if isinstance(model_data, str):
                config.model.model = model_data
            elif isinstance(model_data, dict):
                config.model = ModelConfig(**model_data)
        
        if "permissions" in data:
            perm_data = data["permissions"]
            if isinstance(perm_data, dict):
                config.permissions = PermissionConfig(**perm_data)
        
        if "security" in data:
            sec_data = data["security"]
            if isinstance(sec_data, dict):
                config.security = SecurityConfig(**sec_data)
        
        if "mcp" in data:
            mcp_data = data["mcp"]
            if isinstance(mcp_data, dict):
                config.mcp = MCPConfig(**mcp_data)
        
        if "lsp" in data:
            lsp_data = data["lsp"]
            if isinstance(lsp_data, dict):
                config.lsp = LSPConfig(**lsp_data)
        
        if "interaction" in data:
            ia_data = data["interaction"]
            if isinstance(ia_data, dict):
                config.interaction = InteractionConfig(**ia_data)
            elif isinstance(ia_data, InteractionConfig):
                config.interaction = ia_data

        if "circuit_breaker" in data:
            cb_data = data["circuit_breaker"]
            if isinstance(cb_data, dict):
                config.circuit_breaker = CircuitBreakerConfig(**cb_data)
            elif isinstance(cb_data, CircuitBreakerConfig):
                config.circuit_breaker = cb_data

        if "skill_dirs" in data:
            config.skill_dirs = data["skill_dirs"]

        if "enable_metrics" in data:
            config.enable_metrics = data["enable_metrics"]
        if "enable_events" in data:
            config.enable_events = data["enable_events"]

        return config
    
    def to_core_config(self) -> dict:
        """Convert to core Config format."""
        
        # Build config dict
        config_dict: dict[str, object] = {
            "model": self.model.model,
        }
        
        # Merge model settings
        config_dict.update(self.model.to_dict())
        
        # Add permissions
        config_dict["permissions"] = self.permissions.to_dict()
        
        # Add security
        config_dict["security"] = self.security.to_dict()
        
        # Add MCP
        config_dict["mcp"] = self.mcp.to_dict()
        
        # Add LSP
        config_dict["lsp"] = self.lsp.to_dict()
        
        # Add thinking settings
        if self.model.enable_thinking:
            config_dict["enable_thinking"] = True
            if self.model.thinking_budget:
                config_dict["thinking_budget"] = self.model.thinking_budget

        # Add interaction
        config_dict["interaction"] = self.interaction.to_dict()

        # Add circuit breaker
        config_dict["circuit_breaker"] = self.circuit_breaker.to_dict()

        # Add custom skill directories
        if self.skill_dirs:
            config_dict["skills"] = {"custom_dirs": self.skill_dirs}

        return config_dict
    
# Convenience function for quick config
def config(
    model: Optional[str] = None,
    workdir: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    enable_thinking: bool = False,
    thinking_budget: Optional[int] = None,
    permissions: Optional[dict] = None,
    allowed_roots: Optional[list[str]] = None,
    strict_read_boundary: bool = False,
    skill_dirs: Optional[list[str]] = None,
    **kwargs,
) -> SDKConfig:
    """Create SDKConfig with common options.
    
    Usage:
        from cody.sdk import config
        
        cfg = config(
            model="your-model-name",
            workdir="/path/to/project",
            base_url="https://api.example.com/v1",
            enable_thinking=True,
            permissions={"exec_command": "allow"},
        )
    """
    cfg = SDKConfig(workdir=workdir)
    
    if model:
        cfg.model.model = model
    if api_key:
        cfg.model.api_key = api_key
    if base_url:
        cfg.model.base_url = base_url
    if enable_thinking:
        cfg.model.enable_thinking = True
    if thinking_budget:
        cfg.model.thinking_budget = thinking_budget
    if permissions:
        cfg.permissions.overrides = permissions
    if allowed_roots:
        cfg.security.allowed_roots = allowed_roots
    if strict_read_boundary:
        cfg.security.strict_read_boundary = strict_read_boundary
    if skill_dirs:
        cfg.skill_dirs = skill_dirs

    # Apply any additional kwargs
    for key, value in kwargs.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)
    
    return cfg
