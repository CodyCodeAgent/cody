"""RPC Server for Cody"""

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

from .core import Config, AgentRunner, SessionStore
from .core.errors import CodyAPIError, ErrorCode, ErrorDetail
from .core.skill_manager import SkillManager
from .core.runner import CodyDeps


# ── Request / Response models ────────────────────────────────────────────────


class RunRequest(BaseModel):
    prompt: str
    workdir: Optional[str] = None
    model: Optional[str] = None
    skills: Optional[list] = None
    session_id: Optional[str] = None
    stream: bool = False


class RunResponse(BaseModel):
    status: str = "success"
    output: str
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
    version: str = "0.4.0"


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
    version="0.4.0",
)


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
    """Get the session store (simple factory, no DI overhead)."""
    return SessionStore()


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
        config = Config.load()
        if request.model:
            config.model = request.model
        if request.skills is not None:
            config.skills.enabled = request.skills

        workdir = Path(request.workdir) if request.workdir else Path.cwd()
        runner = AgentRunner(config=config, workdir=workdir)

        if request.session_id is not None:
            # Session-aware run
            store = _get_session_store()
            result, sid = await runner.run_with_session(
                request.prompt, store, request.session_id
            )
        else:
            result = await runner.run(request.prompt)
            sid = None

        return RunResponse(
            output=result.output,
            session_id=sid,
            usage={
                "input_tokens": result.usage().input_tokens,
                "output_tokens": result.usage().output_tokens,
                "total_tokens": result.usage().total_tokens,
            },
        )

    except ValueError as e:
        _raise_structured(
            ErrorCode.SESSION_NOT_FOUND, str(e), status_code=404
        )
    except CodyAPIError:
        raise
    except Exception as e:
        _raise_structured(
            ErrorCode.SERVER_ERROR, str(e), status_code=500
        )


@app.post("/run/stream")
async def run_agent_stream(request: RunRequest):
    """Run agent with streaming response, optionally within a session."""

    async def generate() -> AsyncIterator[str]:
        try:
            config = Config.load()
            if request.model:
                config.model = request.model

            workdir = Path(request.workdir) if request.workdir else Path.cwd()
            runner = AgentRunner(config=config, workdir=workdir)

            if request.session_id is not None:
                store = _get_session_store()
                async for text, sid in runner.run_stream_with_session(
                    request.prompt, store, request.session_id
                ):
                    yield (
                        f"data: {json.dumps({'type': 'text', 'content': text, 'session_id': sid})}"
                        "\n\n"
                    )
            else:
                async for text in runner.run_stream(request.prompt):
                    yield f"data: {json.dumps({'type': 'text', 'content': text})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

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
        config = Config.load()
        workdir = Path(request.workdir) if request.workdir else Path.cwd()
        deps = CodyDeps(
            config=config,
            workdir=workdir,
            skill_manager=SkillManager(config),
        )

        class ToolContext:
            def __init__(self, deps):
                self.deps = deps

        ctx = ToolContext(deps)
        result = await tool_func(ctx, **request.params)

        return ToolResponse(result=result)

    except PermissionError as e:
        _raise_structured(
            ErrorCode.PERMISSION_DENIED, str(e), status_code=403
        )
    except CodyAPIError:
        raise
    except Exception as e:
        _raise_structured(
            ErrorCode.TOOL_ERROR, str(e), status_code=500,
            details={"tool": request.tool},
        )


# ── Skills ───────────────────────────────────────────────────────────────────


@app.get("/skills")
async def list_skills():
    """List all available skills"""
    try:
        config = Config.load()
        skill_manager = SkillManager(config)
        skills = skill_manager.list_skills()

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
async def get_skill(skill_name: str):
    """Get skill documentation"""
    try:
        config = Config.load()
        skill_manager = SkillManager(config)
        skill = skill_manager.get_skill(skill_name)
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


# ── Sub-Agent ────────────────────────────────────────────────────────────────


# Module-level sub-agent manager (shared across requests)
_sub_agent_manager = None


def _get_sub_agent_manager():
    global _sub_agent_manager
    if _sub_agent_manager is None:
        from .core.sub_agent import SubAgentManager
        config = Config.load()
        _sub_agent_manager = SubAgentManager(config=config, workdir=Path.cwd())
    return _sub_agent_manager


class SpawnRequest(BaseModel):
    task: str
    type: str = "generic"
    timeout: Optional[float] = None


@app.post("/agent/spawn")
async def spawn_agent(request: SpawnRequest):
    """Spawn a sub-agent"""
    try:
        manager = _get_sub_agent_manager()
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
    manager = _get_sub_agent_manager()
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
    manager = _get_sub_agent_manager()
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

        workdir_str = data.get("workdir")
        model_str = data.get("model")
        session_id = data.get("session_id")

        self._cancel_event = asyncio.Event()

        try:
            config = Config.load()
            if model_str:
                config.model = model_str

            workdir = Path(workdir_str) if workdir_str else Path.cwd()
            runner = AgentRunner(config=config, workdir=workdir)

            await self.send_event("start", {"session_id": session_id})

            if session_id is not None:
                store = _get_session_store()
                chunks: list[str] = []
                async for text, sid in runner.run_stream_with_session(
                    prompt, store, session_id
                ):
                    if self._cancel_event.is_set():
                        await self.send_event("cancelled")
                        return
                    chunks.append(text)
                    await self.send_event("text", {"content": text, "session_id": sid})
                await self.send_event("done", {
                    "output": "".join(chunks),
                    "session_id": sid,
                })
            else:
                chunks = []
                async for text in runner.run_stream(prompt):
                    if self._cancel_event.is_set():
                        await self.send_event("cancelled")
                        return
                    chunks.append(text)
                    await self.send_event("text", {"content": text})
                await self.send_event("done", {"output": "".join(chunks)})

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
