"""Web backend — independent FastAPI application.

Manages projects in its own SQLite database and proxies AI operations
to the Cody core server via AsyncCodyClient.

Run standalone:
    python -m web.backend.app
"""

from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from .db import ProjectStore
from .models import WebHealthResponse

# ── Singletons ───────────────────────────────────────────────────────────────

_project_store: Optional[ProjectStore] = None
_cody_client = None  # AsyncCodyClient, lazily created


def get_project_store() -> ProjectStore:
    """Get or create the project store singleton."""
    global _project_store
    if _project_store is None:
        _project_store = ProjectStore()
    return _project_store


def get_cody_client():
    """Get or create the AsyncCodyClient singleton."""
    global _cody_client
    if _cody_client is None:
        try:
            from cody.client import AsyncCodyClient
            _cody_client = AsyncCodyClient("http://localhost:8000")
        except Exception:
            return None
    return _cody_client


def _reset_state():
    """Reset singletons for testing."""
    global _project_store, _cody_client
    _project_store = None
    _cody_client = None


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Cody Web Backend",
    description="Web frontend backend — project management and chat proxy",
    version="1.3.0",
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


# ── Routes ───────────────────────────────────────────────────────────────────

from .routes.directories import router as directories_router  # noqa: E402
from .routes import projects as _projects  # noqa: E402
from .routes import chat as _chat  # noqa: E402
from .models import ProjectCreate, ProjectUpdate, ProjectResponse  # noqa: E402

app.include_router(directories_router)


# Projects: inject store + cody_client into all endpoints
@app.get("/api/projects", response_model=list[ProjectResponse])
async def list_projects_endpoint(
    store: ProjectStore = Depends(get_project_store),
):
    return await _projects.list_projects(store=store)


@app.post("/api/projects", response_model=ProjectResponse, status_code=201)
async def create_project_endpoint(
    body: ProjectCreate,
    store: ProjectStore = Depends(get_project_store),
    cody_client=Depends(get_cody_client),
):
    return await _projects.create_project(
        body=body, store=store, cody_client=cody_client
    )


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
    cody_client=Depends(get_cody_client),
):
    return await _projects.delete_project(
        project_id=project_id, store=store, cody_client=cody_client
    )


# Chat WebSocket: inject store + cody_client
@app.websocket("/ws/chat/{project_id}")
async def chat_websocket_endpoint(
    ws: WebSocket,
    project_id: str,
    store: ProjectStore = Depends(get_project_store),
    cody_client=Depends(get_cody_client),
):
    await _chat.chat_websocket(
        ws=ws, project_id=project_id, store=store, cody_client=cody_client
    )


# Health
@app.get("/api/health", response_model=WebHealthResponse)
async def health(cody_client=Depends(get_cody_client)):
    """Check web backend health and core server connectivity."""
    core_status = "unavailable"
    core_version = None
    if cody_client is not None:
        try:
            data = await cody_client.health()
            core_status = "connected"
            core_version = data.get("version")
        except Exception:
            pass

    return WebHealthResponse(
        core_server=core_status,
        core_version=core_version,
    )


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

def run(host: str = "0.0.0.0", port: int = 5001):
    """Run the web backend server."""
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run()
