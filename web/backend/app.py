"""Cody Web Backend — unified FastAPI application.

Serves both web-specific endpoints (projects, directories, chat) and
core RPC endpoints (run, stream, tool, sessions, skills, agents, audit, ws).

All business logic lives in core/. This is a thin shell.

Run standalone:
    cody-web              # production (serves dist/ static files)
    cody-web --dev        # development (also starts Vite dev server)
    cody-web --port 9000  # custom port
"""

import argparse
import atexit
import logging
import os
import subprocess
import sys
from pathlib import Path

try:
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from fastapi.staticfiles import StaticFiles
    import uvicorn
except ImportError:
    raise SystemExit(
        "Web backend requires extra dependencies. Install with:\n"
        "  pip install cody-ai[web]"
    )

from cody import __version__
from cody.core.errors import CodyAPIError
from cody.core.log import setup_logging

from .models import HealthResponse
from .middleware import auth_middleware, rate_limit_middleware, audit_middleware

from .routes.directories import router as directories_router
from .routes.run import router as run_router
from .routes.tool import router as tool_router
from .routes.sessions import router as sessions_router
from .routes.skills import router as skills_router
from .routes.audit_routes import router as audit_router
from .routes.agents import router as agents_router
from .routes.config import router as config_router
from .routes.metrics import router as metrics_router
from .routes.projects import router as projects_router
from .routes.tasks import router as tasks_router
from .routes.task_chat import router as task_chat_router
from .routes.chat import router as chat_router

# ── Logging setup ─────────────────────────────────────────────────────────────

setup_logging()
logger = logging.getLogger("cody.web")


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Cody Server",
    description="AI Coding Assistant — Web frontend + RPC API",
    version=__version__,
)

_DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]
_cors_env = os.environ.get("CODY_CORS_ORIGINS", "")
_cors_origins = (
    [o.strip() for o in _cors_env.split(",") if o.strip()]
    if _cors_env
    else _DEFAULT_ORIGINS
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
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
    logger.warning(
        "CodyAPIError %s %s: [%s] %s",
        request.method, request.url.path, exc.code, exc.message,
    )
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
app.include_router(config_router)
app.include_router(metrics_router)


# ── Web routes ──────────────────────────────────────────────────────────────

app.include_router(directories_router)
app.include_router(projects_router)
# Task-level chat WS must be before project-level to avoid "task" matching as project_id
app.include_router(task_chat_router)
app.include_router(tasks_router)
app.include_router(chat_router)


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

_WEB_DIR = Path(__file__).resolve().parent.parent


def _start_vite() -> subprocess.Popen:
    """Start the Vite dev server as a child process."""
    logger.info("Starting Vite dev server (port 5173)...")
    proc = subprocess.Popen(
        ["npx", "vite", "--host"],
        cwd=str(_WEB_DIR),
        env={**os.environ, "FORCE_COLOR": "1"},
    )
    atexit.register(proc.terminate)
    return proc


def _cmd_run(args):
    """Handle `cody-web run`."""
    has_dist = (_WEB_DIR / "dist" / "index.html").is_file()
    need_vite = args.dev or not has_dist

    vite_proc = None
    if need_vite:
        if not has_dist:
            logger.info("No dist/ found — starting Vite dev server automatically")
        vite_proc = _start_vite()

    mode = "dev (Vite :5173)" if need_vite else "production (dist/)"
    logger.info("Starting Cody Web v%s on %s:%d [%s]", __version__, args.host, args.port, mode)

    try:
        uvicorn.run(app, host=args.host, port=args.port)
    finally:
        if vite_proc:
            logger.info("Stopping Vite dev server...")
            vite_proc.terminate()
            vite_proc.wait(timeout=5)


def _cmd_build(_args):
    """Handle `cody-web build`."""
    logger.info("Building frontend (web/dist/)...")
    result = subprocess.run(
        ["npx", "vite", "build"],
        cwd=str(_WEB_DIR),
    )
    if result.returncode != 0:
        sys.exit(result.returncode)
    logger.info("Build complete → web/dist/")


def run():
    """Entry point for `cody-web` command."""
    parser = argparse.ArgumentParser(
        prog="cody-web",
        description="Cody Web — backend API + frontend UI",
    )
    sub = parser.add_subparsers(dest="command")

    # cody-web run
    run_parser = sub.add_parser("run", help="start backend (+ frontend if needed)")
    run_parser.add_argument("--dev", action="store_true", help="force Vite dev server")
    run_parser.add_argument("--host", default="0.0.0.0", help="bind host (default: 0.0.0.0)")
    run_parser.add_argument("--port", type=int, default=8000, help="bind port (default: 8000)")

    # cody-web build
    sub.add_parser("build", help="build frontend for production")

    args = parser.parse_args()

    if args.command == "build":
        _cmd_build(args)
    elif args.command == "run":
        _cmd_run(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    run()
