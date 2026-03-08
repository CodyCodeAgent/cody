"""Project CRUD routes.

Uses core SessionStore directly (no HTTP SDK). Router registered in app.py.
"""

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends

from cody.core import Config, SessionStore
from cody.core.errors import ErrorCode
from cody.core.project_instructions import generate_project_instructions

from ..db import ProjectStore
from ..helpers import raise_structured
from ..models import ProjectCreate, ProjectUpdate, ProjectResponse
from ..state import get_project_store, session_store_dep

logger = logging.getLogger("cody.web.projects")

router = APIRouter(tags=["projects"])


def _project_response(p) -> ProjectResponse:
    return ProjectResponse(
        id=p.id,
        name=p.name,
        description=p.description,
        workdir=p.workdir,
        code_paths=p.code_paths,
        session_id=p.session_id,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get("/api/projects", response_model=list[ProjectResponse])
async def list_projects(
    store: ProjectStore = Depends(get_project_store),
):
    """List all projects."""
    projects = await asyncio.to_thread(store.list_projects)
    logger.info("List projects: count=%d", len(projects))
    return [_project_response(p) for p in projects]


@router.post("/api/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreate,
    store: ProjectStore = Depends(get_project_store),
    session_store: SessionStore = Depends(session_store_dep),
):
    """Create a new project.

    Initializes .cody/ in workdir and creates a linked cody session.
    """
    logger.info("Create project: name=%s workdir=%s", body.name, body.workdir)
    workdir = Path(body.workdir)
    if not workdir.is_dir():
        logger.warning("Create project: workdir not found: %s", workdir)
        raise_structured(
            ErrorCode.NOT_FOUND,
            f"Directory not found: {workdir}",
            status_code=404,
        )

    # Init .cody/ directory
    cody_dir = workdir / ".cody"
    cody_dir.mkdir(exist_ok=True)
    config_path = cody_dir / "config.json"
    if not config_path.exists():
        config_path.write_text("{}\n")

    # Create project in web DB
    project = await asyncio.to_thread(
        store.create_project,
        name=body.name,
        description=body.description,
        workdir=str(workdir),
        code_paths=body.code_paths,
    )

    # Create a cody session directly via SessionStore
    try:
        session = await asyncio.to_thread(
            session_store.create_session,
            title=body.name, workdir=str(workdir),
        )
        await asyncio.to_thread(store.set_session_id, project.id, session.id)
        project = await asyncio.to_thread(store.get_project, project.id)
        logger.info(
            "Project created: id=%s session=%s", project.id, session.id,
        )
    except Exception as e:
        # Session creation may fail; project still created
        logger.warning(
            "Session creation failed for project %s: %s", project.id, e,
        )

    return _project_response(project)


@router.get("/api/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    store: ProjectStore = Depends(get_project_store),
):
    """Get a project by ID."""
    project = await asyncio.to_thread(store.get_project, project_id)
    if project is None:
        raise_structured(
            ErrorCode.NOT_FOUND, "Project not found", status_code=404,
        )
    return _project_response(project)


@router.put("/api/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    store: ProjectStore = Depends(get_project_store),
):
    """Update project name and/or description."""
    project = await asyncio.to_thread(
        store.update_project,
        project_id, name=body.name, description=body.description,
        code_paths=body.code_paths,
    )
    if project is None:
        raise_structured(
            ErrorCode.NOT_FOUND, "Project not found", status_code=404,
        )
    return _project_response(project)


@router.delete("/api/projects/{project_id}")
async def delete_project(
    project_id: str,
    store: ProjectStore = Depends(get_project_store),
    session_store: SessionStore = Depends(session_store_dep),
):
    """Delete a project."""
    logger.info("Delete project: id=%s", project_id)
    project = await asyncio.to_thread(store.get_project, project_id)
    if project is None:
        logger.warning("Delete project: not found: %s", project_id)
        raise_structured(
            ErrorCode.NOT_FOUND, "Project not found", status_code=404,
        )

    # Try to delete linked cody session
    if project.session_id:
        try:
            await asyncio.to_thread(
                session_store.delete_session, project.session_id,
            )
            logger.info("Deleted linked session: %s", project.session_id)
        except Exception as e:
            logger.warning(
                "Failed to delete session %s: %s", project.session_id, e,
            )

    await asyncio.to_thread(store.delete_project, project_id)
    return {"status": "deleted", "id": project_id}


@router.post("/api/projects/{project_id}/init")
async def init_project_cody_md(
    project_id: str,
    store: ProjectStore = Depends(get_project_store),
):
    """Generate CODY.md for a project using AI analysis (like `cody init`)."""
    logger.info("Init CODY.md: project=%s", project_id)
    project = await asyncio.to_thread(store.get_project, project_id)
    if project is None:
        raise_structured(
            ErrorCode.NOT_FOUND, "Project not found", status_code=404,
        )

    workdir = Path(project.workdir)
    config = Config.load(workdir=workdir)

    try:
        content = await generate_project_instructions(workdir, config)
        cody_md_path = workdir / "CODY.md"
        cody_md_path.write_text(content, encoding="utf-8")
        logger.info(
            "CODY.md generated: project=%s path=%s len=%d",
            project_id, cody_md_path, len(content),
        )
        return {"status": "generated", "path": str(cody_md_path)}
    except Exception as e:
        logger.error(
            "CODY.md generation failed: project=%s error=%s",
            project_id, e, exc_info=True,
        )
        raise_structured(
            ErrorCode.SERVER_ERROR,
            f"Failed to generate CODY.md: {e}",
            status_code=500,
        )
