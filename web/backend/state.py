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


# ── Server-level singletons ─────────────────────────────────────────────────

_audit_logger: Optional[AuditLogger] = None
_auth_manager: Optional[AuthManager] = None
_rate_limiter: Optional[RateLimiter] = None
_rate_limiter_checked = False
_session_store: Optional[SessionStore] = None
_config_cache: dict[str, tuple[Config, float]] = {}
_CONFIG_CACHE_TTL = 60.0  # seconds
_sub_agent_manager = None
_sub_agent_lock = asyncio.Lock()
_project_store: Optional[ProjectStore] = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def get_auth_manager() -> Optional[AuthManager]:
    global _auth_manager
    if _auth_manager is None:
        try:
            config = Config.load(workdir=Path.cwd())
            _auth_manager = AuthManager(config=config.auth)
        except Exception:
            return None
    return _auth_manager


def get_rate_limiter() -> Optional[RateLimiter]:
    global _rate_limiter, _rate_limiter_checked
    if not _rate_limiter_checked:
        _rate_limiter_checked = True
        try:
            config = Config.load(workdir=Path.cwd())
            if config.rate_limit.enabled:
                _rate_limiter = RateLimiter(
                    max_requests=config.rate_limit.max_requests,
                    window_seconds=config.rate_limit.window_seconds,
                )
        except Exception:
            pass
    return _rate_limiter


def get_session_store() -> SessionStore:
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store


def get_config(workdir: Path) -> Config:
    """Get config for a workdir, cached to avoid repeated disk reads.

    Cache entries expire after _CONFIG_CACHE_TTL seconds so config changes
    on disk are picked up without restarting the server.
    """
    key = str(workdir)
    now = time.monotonic()
    if key in _config_cache:
        cached_config, cached_at = _config_cache[key]
        if now - cached_at < _CONFIG_CACHE_TTL:
            return cached_config.model_copy(deep=True)
    _config_cache[key] = (Config.load(workdir=workdir), now)
    return _config_cache[key][0].model_copy(deep=True)


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


def get_project_store() -> ProjectStore:
    global _project_store
    if _project_store is None:
        _project_store = ProjectStore()
    return _project_store


async def get_sub_agent_manager(workdir: Optional[Path] = None):
    global _sub_agent_manager
    if _sub_agent_manager is None:
        async with _sub_agent_lock:
            if _sub_agent_manager is None:
                from cody.core.sub_agent import SubAgentManager
                wd = workdir or Path.cwd()
                config = get_config(wd)
                _sub_agent_manager = SubAgentManager(config=config, workdir=wd)
    return _sub_agent_manager


def reset_state():
    """Reset all singletons for testing."""
    global _audit_logger, _auth_manager, _rate_limiter, _rate_limiter_checked
    global _session_store, _config_cache, _sub_agent_manager, _project_store
    _audit_logger = None
    _auth_manager = None
    _rate_limiter = None
    _rate_limiter_checked = False
    _session_store = None
    _config_cache.clear()
    _sub_agent_manager = None
    _project_store = None
