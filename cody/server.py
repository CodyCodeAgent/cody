"""RPC Server for Cody.

Thin FastAPI shell over the core engine. All business logic lives in core/.

Caching strategy:
  - Config: cached per-workdir, deep-copied on access so request overrides
    don't leak across requests.
  - SessionStore: global singleton (one SQLite connection shared).
  - SkillManager: always created fresh — disk is the source of truth so
    newly added/changed skill files are visible immediately.
  - AuditLogger, AuthManager, RateLimiter: global singletons (config-stable).

Error handling:
  Tool-layer typed exceptions (ToolPermissionDenied, ToolPathDenied,
  ToolInvalidParams) are caught by type and mapped to HTTP 403/400/500.
  CodyAPIError passes through the FastAPI exception_handler. Everything
  else becomes a generic 500.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

from .core import Config, AgentRunner, SessionStore
from .core.audit import AuditLogger, AuditEvent
from .core.auth import AuthError, AuthManager
from .core.errors import (
    CodyAPIError, ErrorCode, ErrorDetail,
    ToolError, ToolPermissionDenied, ToolPathDenied, ToolInvalidParams,
)
from .core.rate_limiter import RateLimiter
from .core.skill_manager import SkillManager
from .core.deps import CodyDeps
from .core.file_history import FileHistory
from .core.permissions import PermissionLevel, PermissionManager


# ── Request / Response models ────────────────────────────────────────────────


class RunRequest(BaseModel):
    prompt: str
    workdir: Optional[str] = None
    allowed_roots: Optional[list[str]] = None
    model: Optional[str] = None
    model_base_url: Optional[str] = None
    model_api_key: Optional[str] = None
    coding_plan_key: Optional[str] = None
    coding_plan_protocol: Optional[str] = None
    enable_thinking: Optional[bool] = None
    thinking_budget: Optional[int] = None
    skills: Optional[list[str]] = None
    session_id: Optional[str] = None


class ToolTraceResponse(BaseModel):
    tool_name: str
    args: dict
    result: str


class RunResponse(BaseModel):
    status: str = "success"
    output: str
    thinking: Optional[str] = None
    tool_traces: Optional[list[ToolTraceResponse]] = None
    session_id: Optional[str] = None
    usage: Optional[dict] = None


class ToolRequest(BaseModel):
    tool: str
    params: dict
    workdir: Optional[str] = None


class ToolResponse(BaseModel):
    status: str = "success"
    result: str


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.3.0"


class ErrorResponse(BaseModel):
    error: ErrorDetail


class SessionResponse(BaseModel):
    id: str
    title: str
    model: str
    workdir: str
    message_count: int
    created_at: str
    updated_at: str


class SessionDetailResponse(SessionResponse):
    messages: list[dict]


# ── App ──────────────────────────────────────────────────────────────────────


app = FastAPI(
    title="Cody RPC Server",
    description="AI Coding Assistant RPC API",
    version="1.3.0",
)


# ── Server-level singletons ─────────────────────────────────────────────────
# These are lazily initialized on first use and live for the process lifetime.
# _reset_server_state() clears them all (used in tests).

_audit_logger: Optional[AuditLogger] = None
_auth_manager: Optional[AuthManager] = None
_rate_limiter: Optional[RateLimiter] = None
_rate_limiter_checked = False


def _get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def _get_auth_manager() -> Optional[AuthManager]:
    global _auth_manager
    if _auth_manager is None:
        try:
            config = Config.load(workdir=Path.cwd())
            _auth_manager = AuthManager(config=config.auth)
        except Exception:
            return None
    return _auth_manager


def _get_rate_limiter() -> Optional[RateLimiter]:
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


# SessionStore: single instance, one SQLite connection for all requests.
_session_store: Optional[SessionStore] = None

# Config: cached per-workdir key. model_copy(deep=True) on read so that
# apply_overrides() in one request doesn't mutate the cached original.
_config_cache: dict[str, Config] = {}


def _reset_server_state():
    """Reset server-level singletons (for testing)."""
    global _audit_logger, _auth_manager, _rate_limiter, _rate_limiter_checked
    global _session_store, _config_cache
    _audit_logger = None
    _auth_manager = None
    _rate_limiter = None
    _rate_limiter_checked = False
    _session_store = None
    _config_cache.clear()


# ── Error handler ────────────────────────────────────────────────────────────


@app.exception_handler(CodyAPIError)
async def cody_api_error_handler(request: Request, exc: CodyAPIError):
    """Convert CodyAPIError to structured JSON response."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_detail(),
    )


def _raise_structured(
    code: ErrorCode,
    message: str,
    status_code: int = 400,
    details: Optional[dict[str, Any]] = None,
):
    """Raise a CodyAPIError with the given fields."""
    raise CodyAPIError(
        code=code,
        message=message,
        status_code=status_code,
        details=details,
    )


def _get_session_store() -> SessionStore:
    """Get the session store singleton."""
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store


def _get_config(workdir: Path) -> Config:
    """Get config for a workdir, cached to avoid repeated disk reads."""
    key = str(workdir)
    if key not in _config_cache:
        _config_cache[key] = Config.load(workdir=workdir)
    return _config_cache[key].model_copy(deep=True)


def _get_skill_manager(config: Config, workdir: Path) -> SkillManager:
    """Create a fresh SkillManager so newly added/changed skills are visible."""
    return SkillManager(config, workdir=workdir)


def _create_full_deps(config: Config, workdir: Path) -> CodyDeps:
    """Create a complete CodyDeps with all optional dependencies populated."""
    return CodyDeps(
        config=config,
        workdir=workdir,
        skill_manager=_get_skill_manager(config, workdir),
        audit_logger=_get_audit_logger(),
        permission_manager=PermissionManager(
            overrides=config.permissions.overrides,
            default_level=PermissionLevel(config.permissions.default_level),
        ),
        file_history=FileHistory(workdir=workdir),
    )


def _config_from_request(request: RunRequest) -> Config:
    """Load config (cached) and apply request-level overrides on a copy."""
    workdir = Path(request.workdir) if request.workdir else Path.cwd()
    return _get_config(workdir).apply_overrides(
        model=request.model,
        model_base_url=request.model_base_url,
        model_api_key=request.model_api_key,
        coding_plan_key=request.coding_plan_key,
        coding_plan_protocol=request.coding_plan_protocol,
        enable_thinking=request.enable_thinking,
        thinking_budget=request.thinking_budget,
        skills=request.skills,
        extra_roots=request.allowed_roots,
    )


# ── Middleware: Auth ─────────────────────────────────────────────────────────

# Endpoints that do not require authentication
_PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Authenticate requests using Bearer token or API key."""
    path = request.url.path
    # Skip auth for public endpoints and WebSocket upgrade
    if path in _PUBLIC_PATHS or path.startswith("/docs"):
        return await call_next(request)

    try:
        auth_mgr = _get_auth_manager()
    except Exception:
        return await call_next(request)

    if auth_mgr is None or not auth_mgr.is_configured:
        # Auth not configured — allow all
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        try:
            _get_audit_logger().log(
                event=AuditEvent.AUTH_FAILURE,
                args_summary=f"path={path}",
                result_summary="Missing Authorization header",
                success=False,
            )
        except Exception:
            pass
        return JSONResponse(
            status_code=401,
            content={"error": {"code": "AUTH_FAILED", "message": "Missing Authorization header"}},
        )

    # Support "Bearer <token>" and raw key
    credential = auth_header
    if auth_header.startswith("Bearer "):
        credential = auth_header[7:]

    try:
        auth_mgr.validate(credential)
    except AuthError as e:
        try:
            _get_audit_logger().log(
                event=AuditEvent.AUTH_FAILURE,
                args_summary=f"path={path}",
                result_summary=str(e),
                success=False,
            )
        except Exception:
            pass
        return JSONResponse(
            status_code=401,
            content={"error": {"code": "AUTH_FAILED", "message": str(e)}},
        )

    return await call_next(request)


# ── Middleware: Rate limiting ────────────────────────────────────────────────


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Apply rate limiting based on client IP."""
    try:
        limiter = _get_rate_limiter()
    except Exception:
        return await call_next(request)

    if limiter is None:
        return await call_next(request)

    path = request.url.path
    if path in _PUBLIC_PATHS:
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    result = limiter.hit(client_ip)

    if not result.allowed:
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": ErrorCode.RATE_LIMITED.value,
                    "message": "Rate limit exceeded",
                }
            },
            headers={
                "Retry-After": str(int(result.retry_after or 1)),
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": "0",
            },
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(result.limit)
    response.headers["X-RateLimit-Remaining"] = str(result.remaining)
    return response


# ── Middleware: Audit ────────────────────────────────────────────────────────


@app.middleware("http")
async def audit_middleware(request: Request, call_next):
    """Log all API requests to the audit log."""
    path = request.url.path
    if path in _PUBLIC_PATHS:
        return await call_next(request)

    start = time.monotonic()
    response = await call_next(request)
    elapsed_ms = int((time.monotonic() - start) * 1000)

    try:
        _get_audit_logger().log(
            event=AuditEvent.API_REQUEST,
            tool_name=f"{request.method} {path}",
            args_summary=f"client={request.client.host if request.client else 'unknown'}",
            result_summary=f"status={response.status_code} elapsed={elapsed_ms}ms",
            success=response.status_code < 400,
        )
    except Exception:
        pass

    return response


# ── Health ───────────────────────────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint"""
    return HealthResponse()


# ── Run ──────────────────────────────────────────────────────────────────────


@app.post("/run", response_model=RunResponse)
async def run_agent(request: RunRequest):
    """Run agent with prompt, optionally within a session."""
    try:
        config = _config_from_request(request)
        workdir = Path(request.workdir) if request.workdir else Path.cwd()
        extra_roots = [Path(r) for r in (request.allowed_roots or [])]
        runner = AgentRunner(config=config, workdir=workdir, extra_roots=extra_roots)

        if request.session_id is not None:
            # Session-aware run
            store = _get_session_store()
            result, sid = await runner.run_with_session(
                request.prompt, store, request.session_id
            )
        else:
            result = await runner.run(request.prompt)
            sid = None

        # Build tool traces for response
        traces = None
        if result.tool_traces:
            traces = [
                ToolTraceResponse(
                    tool_name=t.tool_name,
                    args=t.args,
                    result=t.result[:500] if t.result else "",
                )
                for t in result.tool_traces
            ]

        usage_data = None
        usage = result.usage()
        if usage:
            usage_data = {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
            }

        return RunResponse(
            output=result.output,
            thinking=result.thinking,
            tool_traces=traces,
            session_id=sid,
            usage=usage_data,
        )

    except (ToolPermissionDenied, ToolPathDenied) as e:
        _raise_structured(e.code, e.message, status_code=403)
    except ToolError as e:
        _raise_structured(e.code, e.message, status_code=400)
    except ValueError as e:
        msg = str(e)
        if "Session not found" in msg:
            _raise_structured(ErrorCode.SESSION_NOT_FOUND, msg, status_code=404)
        else:
            _raise_structured(ErrorCode.INVALID_PARAMS, msg, status_code=400)
    except CodyAPIError:
        raise
    except Exception as e:
        _raise_structured(
            ErrorCode.SERVER_ERROR, str(e), status_code=500
        )


def _serialize_stream_event(event, session_id: Optional[str] = None) -> dict:
    """Convert a StreamEvent to a JSON-serializable dict for SSE/WebSocket."""
    from .core.runner import (
        CompactEvent, ThinkingEvent, TextDeltaEvent, ToolCallEvent,
        ToolResultEvent, DoneEvent,
    )

    base: dict[str, Any] = {"type": event.event_type}
    if session_id:
        base["session_id"] = session_id

    if isinstance(event, CompactEvent):
        base["original_messages"] = event.original_messages
        base["compacted_messages"] = event.compacted_messages
        base["estimated_tokens_saved"] = event.estimated_tokens_saved
    elif isinstance(event, ThinkingEvent):
        base["content"] = event.content
    elif isinstance(event, TextDeltaEvent):
        base["content"] = event.content
    elif isinstance(event, ToolCallEvent):
        base["tool_name"] = event.tool_name
        base["args"] = event.args
        base["tool_call_id"] = event.tool_call_id
    elif isinstance(event, ToolResultEvent):
        base["tool_name"] = event.tool_name
        base["tool_call_id"] = event.tool_call_id
        base["result"] = event.result[:500]
    elif isinstance(event, DoneEvent):
        base["output"] = event.result.output
        base["thinking"] = event.result.thinking
        if event.result.tool_traces:
            base["tool_traces"] = [
                {
                    "tool_name": t.tool_name,
                    "args": t.args,
                    "result": t.result[:500],
                }
                for t in event.result.tool_traces
            ]
        usage = event.result.usage()
        if usage:
            base["usage"] = {
                "total_tokens": usage.total_tokens,
            }

    return base


@app.post("/run/stream")
async def run_agent_stream(request: RunRequest):
    """Run agent with streaming response, emitting structured events."""

    async def generate() -> AsyncIterator[str]:
        try:
            config = _config_from_request(request)
            workdir = Path(request.workdir) if request.workdir else Path.cwd()
            extra_roots = [Path(r) for r in (request.allowed_roots or [])]
            runner = AgentRunner(config=config, workdir=workdir, extra_roots=extra_roots)

            if request.session_id is not None:
                store = _get_session_store()
                async for event, sid in runner.run_stream_with_session(
                    request.prompt, store, request.session_id
                ):
                    yield f"data: {json.dumps(_serialize_stream_event(event, session_id=sid))}\n\n"
            else:
                async for event in runner.run_stream(request.prompt):
                    yield f"data: {json.dumps(_serialize_stream_event(event))}\n\n"

        except Exception as e:
            error_payload = {
                "type": "error",
                "error": {
                    "code": ErrorCode.SERVER_ERROR.value,
                    "message": str(e),
                },
            }
            yield f"data: {json.dumps(error_payload)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Tool ─────────────────────────────────────────────────────────────────────


@app.post("/tool", response_model=ToolResponse)
async def call_tool(request: ToolRequest):
    """Call a tool directly"""
    from .core import tools

    tool_func = getattr(tools, request.tool, None)
    if not tool_func:
        _raise_structured(
            ErrorCode.TOOL_NOT_FOUND,
            f"Tool not found: {request.tool}",
            status_code=404,
        )

    try:
        workdir = Path(request.workdir) if request.workdir else Path.cwd()
        config = _get_config(workdir)
        deps = _create_full_deps(config, workdir)

        # Shim: tools expect RunContext[CodyDeps] but we only need ctx.deps.
        # A lightweight object avoids pulling in pydantic-ai Agent machinery.
        class ToolContext:
            def __init__(self, deps):
                self.deps = deps

        ctx = ToolContext(deps)
        result = await tool_func(ctx, **request.params)

        return ToolResponse(result=result)

    except (ToolPermissionDenied, ToolPathDenied) as e:
        _raise_structured(e.code, e.message, status_code=403)
    except ToolInvalidParams as e:
        _raise_structured(e.code, e.message, status_code=400)
    except ToolError as e:
        _raise_structured(e.code, e.message, status_code=500)
    except CodyAPIError:
        raise
    except Exception as e:
        _raise_structured(
            ErrorCode.TOOL_ERROR, str(e), status_code=500,
            details={"tool": request.tool},
        )


# ── Skills ───────────────────────────────────────────────────────────────────


@app.get("/skills")
async def list_skills(workdir: Optional[str] = None):
    """List all available skills"""
    try:
        wd = Path(workdir) if workdir else Path.cwd()
        config = _get_config(wd)
        sm = _get_skill_manager(config, wd)
        skills = sm.list_skills()

        return {
            "skills": [
                {
                    "name": skill.name,
                    "description": skill.description,
                    "enabled": skill.enabled,
                    "source": skill.source,
                }
                for skill in skills
            ]
        }

    except CodyAPIError:
        raise
    except Exception as e:
        _raise_structured(
            ErrorCode.SERVER_ERROR, str(e), status_code=500
        )


@app.get("/skills/{skill_name}")
async def get_skill(skill_name: str, workdir: Optional[str] = None):
    """Get skill documentation"""
    try:
        wd = Path(workdir) if workdir else Path.cwd()
        config = _get_config(wd)
        sm = _get_skill_manager(config, wd)
        skill = sm.get_skill(skill_name)
        if not skill:
            _raise_structured(
                ErrorCode.SKILL_NOT_FOUND,
                f"Skill not found: {skill_name}",
                status_code=404,
            )

        return {
            "name": skill.name,
            "description": skill.description,
            "enabled": skill.enabled,
            "source": skill.source,
            "documentation": skill.documentation,
        }

    except CodyAPIError:
        raise
    except Exception as e:
        _raise_structured(
            ErrorCode.SERVER_ERROR, str(e), status_code=500
        )


# ── Sessions ─────────────────────────────────────────────────────────────────


@app.post("/sessions", response_model=SessionResponse)
async def create_session(
    title: str = "New session",
    model: str = "",
    workdir: str = "",
):
    """Create a new session"""
    store = _get_session_store()
    session = store.create_session(title=title, model=model, workdir=workdir)
    return SessionResponse(
        id=session.id,
        title=session.title,
        model=session.model,
        workdir=session.workdir,
        message_count=0,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@app.get("/sessions")
async def list_sessions(limit: int = 20):
    """List recent sessions"""
    store = _get_session_store()
    sessions = store.list_sessions(limit=limit)
    return {
        "sessions": [
            {
                "id": s.id,
                "title": s.title,
                "model": s.model,
                "workdir": s.workdir,
                "message_count": store.get_message_count(s.id),
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            }
            for s in sessions
        ]
    }


@app.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(session_id: str):
    """Get session with messages"""
    store = _get_session_store()
    session = store.get_session(session_id)
    if not session:
        _raise_structured(
            ErrorCode.SESSION_NOT_FOUND,
            f"Session not found: {session_id}",
            status_code=404,
        )

    return SessionDetailResponse(
        id=session.id,
        title=session.title,
        model=session.model,
        workdir=session.workdir,
        message_count=len(session.messages),
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[
            {"role": m.role, "content": m.content, "timestamp": m.timestamp}
            for m in session.messages
        ],
    )


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session"""
    store = _get_session_store()
    deleted = store.delete_session(session_id)
    if not deleted:
        _raise_structured(
            ErrorCode.SESSION_NOT_FOUND,
            f"Session not found: {session_id}",
            status_code=404,
        )
    return {"status": "deleted", "id": session_id}


# ── Audit ────────────────────────────────────────────────────────────────────


@app.get("/audit")
async def query_audit(
    event: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = 50,
):
    """Query audit log entries"""
    logger = _get_audit_logger()
    entries = logger.query(event=event, since=since, limit=limit)
    return {
        "entries": [
            {
                "id": e.id,
                "timestamp": e.timestamp,
                "event": e.event,
                "tool_name": e.tool_name,
                "args_summary": e.args_summary,
                "result_summary": e.result_summary,
                "session_id": e.session_id,
                "workdir": e.workdir,
                "success": e.success,
            }
            for e in entries
        ],
        "total": logger.count(event=event),
    }


# ── Sub-Agent ────────────────────────────────────────────────────────────────


# Sub-agent manager factory. Uses a lock to ensure safe lazy init.
_sub_agent_manager = None
_sub_agent_lock = asyncio.Lock()


async def _get_sub_agent_manager(workdir: Optional[Path] = None):
    global _sub_agent_manager
    if _sub_agent_manager is None:
        async with _sub_agent_lock:
            if _sub_agent_manager is None:
                from .core.sub_agent import SubAgentManager
                wd = workdir or Path.cwd()
                config = _get_config(wd)
                _sub_agent_manager = SubAgentManager(config=config, workdir=wd)
    return _sub_agent_manager


class SpawnRequest(BaseModel):
    task: str
    type: str = "generic"
    timeout: Optional[float] = None
    workdir: Optional[str] = None


@app.post("/agent/spawn")
async def spawn_agent(request: SpawnRequest):
    """Spawn a sub-agent"""
    try:
        wd = Path(request.workdir) if request.workdir else Path.cwd()
        manager = await _get_sub_agent_manager(workdir=wd)
        agent_id = await manager.spawn(
            request.task, request.type, request.timeout
        )
        result = manager.get_status(agent_id)
        return {
            "agent_id": agent_id,
            "status": result.status if result else "pending",
            "created_at": result.created_at if result else "",
        }
    except RuntimeError as e:
        _raise_structured(
            ErrorCode.AGENT_LIMIT_REACHED, str(e), status_code=429
        )
    except CodyAPIError:
        raise
    except Exception as e:
        _raise_structured(
            ErrorCode.AGENT_ERROR, str(e), status_code=500
        )


@app.get("/agent/{agent_id}")
async def get_agent_status(agent_id: str):
    """Get sub-agent status"""
    manager = await _get_sub_agent_manager(Path.cwd())
    result = manager.get_status(agent_id)
    if result is None:
        _raise_structured(
            ErrorCode.AGENT_NOT_FOUND,
            f"Agent not found: {agent_id}",
            status_code=404,
        )
    return {
        "agent_id": result.agent_id,
        "status": result.status,
        "output": result.output,
        "error": result.error,
        "created_at": result.created_at,
        "completed_at": result.completed_at,
    }


@app.delete("/agent/{agent_id}")
async def kill_agent(agent_id: str):
    """Kill a running sub-agent"""
    manager = await _get_sub_agent_manager(Path.cwd())
    result = manager.get_status(agent_id)
    if result is None:
        _raise_structured(
            ErrorCode.AGENT_NOT_FOUND,
            f"Agent not found: {agent_id}",
            status_code=404,
        )
    killed = await manager.kill(agent_id)
    return {
        "agent_id": agent_id,
        "killed": killed,
        "status": "killed" if killed else result.status,
    }


# ── WebSocket ────────────────────────────────────────────────────────────────


class _WSConnection:
    """Manage a single WebSocket connection for agent interaction."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self._cancel_event: Optional[asyncio.Event] = None

    async def accept(self):
        await self.ws.accept()

    async def send_event(self, event_type: str, data: Optional[dict] = None):
        payload: dict[str, Any] = {"type": event_type}
        if data:
            payload.update(data)
        await self.ws.send_json(payload)

    async def handle(self):
        """Main receive loop."""
        try:
            while True:
                raw = await self.ws.receive_json()
                msg_type = raw.get("type", "")

                if msg_type == "run":
                    await self._handle_run(raw.get("data", {}))
                elif msg_type == "cancel":
                    if self._cancel_event:
                        self._cancel_event.set()
                    await self.send_event("cancelled")
                elif msg_type == "ping":
                    await self.send_event("pong")
                else:
                    await self.send_event("error", {
                        "error": {
                            "code": ErrorCode.INVALID_PARAMS.value,
                            "message": f"Unknown message type: {msg_type}",
                        }
                    })

        except WebSocketDisconnect:
            pass

    async def _handle_run(self, data: dict):
        prompt = data.get("prompt", "")
        if not prompt:
            await self.send_event("error", {
                "error": {
                    "code": ErrorCode.INVALID_PARAMS.value,
                    "message": "prompt is required",
                }
            })
            return

        session_id = data.get("session_id")

        self._cancel_event = asyncio.Event()

        try:
            workdir = Path(data["workdir"]) if data.get("workdir") else Path.cwd()
            config = _get_config(workdir).apply_overrides(
                model=data.get("model"),
                model_base_url=data.get("model_base_url"),
                model_api_key=data.get("model_api_key"),
                coding_plan_key=data.get("coding_plan_key"),
                coding_plan_protocol=data.get("coding_plan_protocol"),
                enable_thinking=data.get("enable_thinking"),
                thinking_budget=data.get("thinking_budget"),
                extra_roots=data.get("allowed_roots"),
            )
            extra_roots = [Path(r) for r in (data.get("allowed_roots") or [])]
            runner = AgentRunner(config=config, workdir=workdir, extra_roots=extra_roots)

            await self.send_event("start", {"session_id": session_id})

            if session_id is not None:
                store = _get_session_store()
                async for event, sid in runner.run_stream_with_session(
                    prompt, store, session_id
                ):
                    if self._cancel_event.is_set():
                        await self.send_event("cancelled")
                        return
                    payload = _serialize_stream_event(event, session_id=sid)
                    await self.send_event(
                        payload.pop("type"), payload
                    )
            else:
                async for event in runner.run_stream(prompt):
                    if self._cancel_event.is_set():
                        await self.send_event("cancelled")
                        return
                    payload = _serialize_stream_event(event)
                    await self.send_event(
                        payload.pop("type"), payload
                    )

        except Exception as e:
            await self.send_event("error", {
                "error": {
                    "code": ErrorCode.SERVER_ERROR.value,
                    "message": str(e),
                }
            })

        finally:
            self._cancel_event = None


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket endpoint for real-time bidirectional interaction."""
    conn = _WSConnection(ws)
    await conn.accept()
    await conn.handle()


# ── Entry point ──────────────────────────────────────────────────────────────


def run(host: str = "0.0.0.0", port: int = 8000):
    """Run the server"""
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import click

    @click.command()
    @click.option('--host', default="0.0.0.0", help='Host to bind')
    @click.option('--port', default=8000, help='Port to bind')
    def main(host, port):
        """Start Cody RPC Server"""
        print(f"Starting Cody RPC Server on {host}:{port}")
        run(host, port)

    main()
