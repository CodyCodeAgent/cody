"""Cody Web Backend — unified FastAPI application.

Serves both web-specific endpoints (projects, directories, chat) and
core RPC endpoints (run, stream, tool, sessions, skills, agents, audit, ws).

All business logic lives in core/. This is a thin shell.

Run standalone:
    python -m web.backend.app
"""

from pathlib import Path

from fastapi import Depends, FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from cody import __version__
from cody.core.errors import CodyAPIError

from .db import ProjectStore
from .models import HealthResponse, ProjectCreate, ProjectUpdate, ProjectResponse
from .state import get_project_store
from .middleware import auth_middleware, rate_limit_middleware, audit_middleware

# ── Route imports ───────────────────────────────────────────────────────────

from .routes.directories import router as directories_router
from .routes.run import router as run_router
from .routes.tool import router as tool_router
from .routes.sessions import router as sessions_router
from .routes.skills import router as skills_router
from .routes.audit_routes import router as audit_router
from .routes.agents import router as agents_router
from .routes.websocket import router as ws_router
from .routes import projects as _projects
from .routes import chat as _chat


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Cody Server",
    description="AI Coding Assistant — Web frontend + RPC API",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Middleware (order matters: outermost runs first) ─────────────────────────

app.middleware("http")(audit_middleware)
app.middleware("http")(rate_limit_middleware)
app.middleware("http")(auth_middleware)


# ── Error handler ───────────────────────────────────────────────────────────

@app.exception_handler(CodyAPIError)
async def cody_api_error_handler(request: Request, exc: CodyAPIError):
    """Convert CodyAPIError to structured JSON response."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_detail(),
    )


# ── RPC routes (migrated from server.py) ────────────────────────────────────

app.include_router(run_router)
app.include_router(tool_router)
app.include_router(sessions_router)
app.include_router(skills_router)
app.include_router(audit_router)
app.include_router(agents_router)
app.include_router(ws_router)


# ── Web routes ──────────────────────────────────────────────────────────────

app.include_router(directories_router)


@app.get("/api/projects", response_model=list[ProjectResponse])
async def list_projects_endpoint(
    store: ProjectStore = Depends(get_project_store),
):
    return await _projects.list_projects(store=store)


@app.post("/api/projects", response_model=ProjectResponse, status_code=201)
async def create_project_endpoint(
    body: ProjectCreate,
    store: ProjectStore = Depends(get_project_store),
):
    return await _projects.create_project(body=body, store=store)


@app.get("/api/projects/{project_id}", response_model=ProjectResponse)
async def get_project_endpoint(
    project_id: str,
    store: ProjectStore = Depends(get_project_store),
):
    return await _projects.get_project(project_id=project_id, store=store)


@app.put("/api/projects/{project_id}", response_model=ProjectResponse)
async def update_project_endpoint(
    project_id: str,
    body: ProjectUpdate,
    store: ProjectStore = Depends(get_project_store),
):
    return await _projects.update_project(
        project_id=project_id, body=body, store=store
    )


@app.delete("/api/projects/{project_id}")
async def delete_project_endpoint(
    project_id: str,
    store: ProjectStore = Depends(get_project_store),
):
    return await _projects.delete_project(project_id=project_id, store=store)


# Chat WebSocket
@app.websocket("/ws/chat/{project_id}")
async def chat_websocket_endpoint(
    ws: WebSocket,
    project_id: str,
    store: ProjectStore = Depends(get_project_store),
):
    await _chat.chat_websocket(ws=ws, project_id=project_id, store=store)


# Health (RPC endpoint)
@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse()


# Health (Web API endpoint)
@app.get("/api/health")
async def api_health():
    """Web frontend health check — no separate core server needed."""
    return {"status": "ok", "version": __version__}


# ── Static files (production) ───────────────────────────────────────────────

_WEB_DIST = Path(__file__).resolve().parent.parent / "dist"
if _WEB_DIST.is_dir() and (_WEB_DIST / "assets").is_dir():
    app.mount(
        "/assets", StaticFiles(directory=_WEB_DIST / "assets"), name="web-assets"
    )

# SPA fallback — must be registered after all API routes
if _WEB_DIST.is_dir():
    @app.get("/", include_in_schema=False)
    async def serve_index():
        from fastapi.responses import FileResponse
        return FileResponse(_WEB_DIST / "index.html")

    @app.get("/{path:path}", include_in_schema=False)
    async def serve_spa_fallback(path: str):
        from fastapi.responses import FileResponse
        file_path = _WEB_DIST / path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_WEB_DIST / "index.html")


# ── Entry point ──────────────────────────────────────────────────────────────

def run(host: str = "0.0.0.0", port: int = 8000):
    """Run the server."""
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
