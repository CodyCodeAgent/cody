"""Server-level singletons and state management.

Migrated from cody/server.py — all shared state lives here.

Caching strategy:
  - Config: cached per-workdir, deep-copied on access so request overrides
    don't leak across requests.
  - SessionStore: global singleton (one SQLite connection shared).
  - SkillManager: always created fresh — disk is the source of truth so
    newly added/changed skill files are visible immediately.
  - AuditLogger, AuthManager, RateLimiter: global singletons (config-stable).
  - ProjectStore: global singleton for web.db.

All mutable state is encapsulated in the ServerState class to avoid
module-level globals and improve testability / thread safety.
"""

import asyncio
import time
from pathlib import Path
from typing import Optional

from cody.core import Config, SessionStore
from cody.core.audit import AuditLogger
from cody.core.auth import AuthManager
from cody.core.deps import CodyDeps
from cody.core.file_history import FileHistory
from cody.core.permissions import PermissionLevel, PermissionManager
from cody.core.rate_limiter import RateLimiter
from cody.core.skill_manager import SkillManager

from .db import ProjectStore


_CONFIG_CACHE_TTL = 60.0  # seconds
_RUNNER_CACHE_TTL = 300.0  # 5 minutes


class ServerState:
    """Encapsulates all server-level mutable singletons."""

    def __init__(self):
        self.audit_logger: Optional[AuditLogger] = None
        self.auth_manager: Optional[AuthManager] = None
        self.rate_limiter: Optional[RateLimiter] = None
        self.rate_limiter_checked: bool = False
        self.session_store: Optional[SessionStore] = None
        self.config_cache: dict[str, tuple[Config, float]] = {}
        self.sub_agent_manager = None
        self.sub_agent_lock: asyncio.Lock = asyncio.Lock()
        self.project_store: Optional[ProjectStore] = None
        self.runner_cache: dict[str, tuple] = {}  # key -> (AgentRunner, created_at, fingerprint)


_state = ServerState()


def get_audit_logger() -> AuditLogger:
    if _state.audit_logger is None:
        _state.audit_logger = AuditLogger()
    return _state.audit_logger


def get_auth_manager() -> Optional[AuthManager]:
    if _state.auth_manager is None:
        try:
            config = Config.load(workdir=Path.cwd())
            _state.auth_manager = AuthManager(config=config.auth)
        except Exception:
            return None
    return _state.auth_manager


def get_rate_limiter() -> Optional[RateLimiter]:
    if not _state.rate_limiter_checked:
        _state.rate_limiter_checked = True
        try:
            config = Config.load(workdir=Path.cwd())
            if config.rate_limit.enabled:
                _state.rate_limiter = RateLimiter(
                    max_requests=config.rate_limit.max_requests,
                    window_seconds=config.rate_limit.window_seconds,
                )
        except Exception:
            pass
    return _state.rate_limiter


def get_session_store() -> SessionStore:
    if _state.session_store is None:
        _state.session_store = SessionStore()
    return _state.session_store


def get_config(workdir: Path) -> Config:
    """Get config for a workdir, cached to avoid repeated disk reads.

    Cache entries expire after _CONFIG_CACHE_TTL seconds so config changes
    on disk are picked up without restarting the server.
    """
    key = str(workdir)
    now = time.monotonic()
    if key in _state.config_cache:
        cached_config, cached_at = _state.config_cache[key]
        if now - cached_at < _CONFIG_CACHE_TTL:
            return cached_config.model_copy(deep=True)
    _state.config_cache[key] = (Config.load(workdir=workdir), now)
    return _state.config_cache[key][0].model_copy(deep=True)


def get_skill_manager(config: Config, workdir: Path) -> SkillManager:
    """Create a fresh SkillManager so newly added/changed skills are visible."""
    return SkillManager(config, workdir=workdir)


def create_full_deps(config: Config, workdir: Path) -> CodyDeps:
    """Create a complete CodyDeps with all optional dependencies populated."""
    return CodyDeps(
        config=config,
        workdir=workdir,
        skill_manager=get_skill_manager(config, workdir),
        allowed_roots=[workdir],
        audit_logger=get_audit_logger(),
        permission_manager=PermissionManager(
            overrides=config.permissions.overrides,
            default_level=PermissionLevel(config.permissions.default_level),
        ),
        file_history=FileHistory(workdir=workdir),
    )


def _config_fingerprint(config: Config) -> str:
    """Return a short fingerprint of config fields that affect the agent."""
    return f"{config.model}|{config.model_base_url}|{config.model_api_key}|{config.enable_thinking}"


def get_runner(workdir: Path):
    """Get or create a cached AgentRunner for the given workdir.

    Avoids re-creating the agent, tools, skill manager, etc. on every message.
    Cache entries expire after _RUNNER_CACHE_TTL seconds or when the model
    config changes (e.g. user switches model in Settings).
    """
    from cody.core import AgentRunner

    key = str(workdir)
    now = time.monotonic()
    config = get_config(workdir)
    fp = _config_fingerprint(config)

    if key in _state.runner_cache:
        runner, created_at, cached_fp = _state.runner_cache[key]
        if now - created_at < _RUNNER_CACHE_TTL and cached_fp == fp:
            return runner

    runner = AgentRunner(config=config, workdir=workdir)
    _state.runner_cache[key] = (runner, now, fp)
    return runner


def get_project_store() -> ProjectStore:
    if _state.project_store is None:
        _state.project_store = ProjectStore()
    return _state.project_store


async def get_sub_agent_manager(workdir: Optional[Path] = None):
    if _state.sub_agent_manager is None:
        async with _state.sub_agent_lock:
            if _state.sub_agent_manager is None:
                from cody.core.sub_agent import SubAgentManager
                wd = workdir or Path.cwd()
                config = get_config(wd)
                _state.sub_agent_manager = SubAgentManager(config=config, workdir=wd)
    return _state.sub_agent_manager


# ── FastAPI Depends() wrappers ───────────────────────────────────────────────
# Parameterless singletons only — config/runner need workdir from request body
# so they remain as direct calls in route handlers.


def session_store_dep() -> SessionStore:
    """FastAPI dependency for SessionStore."""
    return get_session_store()


def project_store_dep() -> ProjectStore:
    """FastAPI dependency for ProjectStore."""
    return get_project_store()


def audit_logger_dep() -> AuditLogger:
    """FastAPI dependency for AuditLogger."""
    return get_audit_logger()


def reset_state():
    """Reset all singletons for testing."""
    global _state
    _state = ServerState()
