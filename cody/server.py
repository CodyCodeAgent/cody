"""RPC Server for Cody"""

import json
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

from .core import Config, AgentRunner, SessionStore
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
    version: str = "0.1.0"


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
    version="0.1.0",
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
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
                    yield f"data: {json.dumps({'type': 'text', 'content': text, 'session_id': sid})}\n\n"
            else:
                async for text in runner.run_stream(request.prompt):
                    yield f"data: {json.dumps({'type': 'text', 'content': text})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Tool ─────────────────────────────────────────────────────────────────────


@app.post("/tool", response_model=ToolResponse)
async def call_tool(request: ToolRequest):
    """Call a tool directly"""
    from .core import tools

    tool_func = getattr(tools, request.tool, None)
    if not tool_func:
        raise HTTPException(status_code=404, detail=f"Tool not found: {request.tool}")

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

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/skills/{skill_name}")
async def get_skill(skill_name: str):
    """Get skill documentation"""
    try:
        config = Config.load()
        skill_manager = SkillManager(config)
        skill = skill_manager.get_skill(skill_name)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")

        return {
            "name": skill.name,
            "description": skill.description,
            "enabled": skill.enabled,
            "source": skill.source,
            "documentation": skill.documentation,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

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
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return {"status": "deleted", "id": session_id}


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
