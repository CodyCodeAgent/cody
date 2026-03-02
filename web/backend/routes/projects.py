"""Project CRUD business logic.

Uses core SessionStore directly (no HTTP SDK). These are plain async
functions called by app.py with injected dependencies.
"""

import logging
from pathlib import Path

from fastapi import HTTPException

from cody.core import Config
from cody.core.project_instructions import generate_project_instructions

from ..db import ProjectStore
from ..models import ProjectCreate, ProjectUpdate, ProjectResponse
from ..state import get_session_store

logger = logging.getLogger("cody.web.projects")


def _project_response(p) -> ProjectResponse:
    return ProjectResponse(
        id=p.id,
        name=p.name,
        description=p.description,
        workdir=p.workdir,
        session_id=p.session_id,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


async def list_projects(store: ProjectStore):
    """List all projects."""
    projects = store.list_projects()
    logger.info("List projects: count=%d", len(projects))
    return [_project_response(p) for p in projects]


async def create_project(body: ProjectCreate, store: ProjectStore):
    """Create a new project.

    Initializes .cody/ in workdir and creates a linked cody session.
    """
    logger.info("Create project: name=%s workdir=%s", body.name, body.workdir)
    workdir = Path(body.workdir)
    if not workdir.is_dir():
        logger.warning("Create project: workdir not found: %s", workdir)
        raise HTTPException(
            status_code=404, detail=f"Directory not found: {workdir}"
        )

    # Init .cody/ directory
    cody_dir = workdir / ".cody"
    cody_dir.mkdir(exist_ok=True)
    config_path = cody_dir / "config.json"
    if not config_path.exists():
        config_path.write_text("{}\n")

    # Create project in web DB
    project = store.create_project(
        name=body.name,
        description=body.description,
        workdir=str(workdir),
    )

    # Create a cody session directly via SessionStore
    try:
        session_store = get_session_store()
        session = session_store.create_session(
            title=body.name, workdir=str(workdir)
        )
        store.set_session_id(project.id, session.id)
        project = store.get_project(project.id)
        logger.info(
            "Project created: id=%s session=%s", project.id, session.id,
        )
    except Exception as e:
        # Session creation may fail; project still created
        logger.warning(
            "Session creation failed for project %s: %s", project.id, e,
        )

    return _project_response(project)


async def get_project(project_id: str, store: ProjectStore):
    """Get a project by ID."""
    project = store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return _project_response(project)


async def update_project(project_id: str, body: ProjectUpdate,
                         store: ProjectStore):
    """Update project name and/or description."""
    project = store.update_project(
        project_id, name=body.name, description=body.description
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return _project_response(project)


async def delete_project(project_id: str, store: ProjectStore):
    """Delete a project."""
    logger.info("Delete project: id=%s", project_id)
    project = store.get_project(project_id)
    if project is None:
        logger.warning("Delete project: not found: %s", project_id)
        raise HTTPException(status_code=404, detail="Project not found")

    # Try to delete linked cody session
    if project.session_id:
        try:
            session_store = get_session_store()
            session_store.delete_session(project.session_id)
            logger.info("Deleted linked session: %s", project.session_id)
        except Exception as e:
            logger.warning(
                "Failed to delete session %s: %s", project.session_id, e,
            )

    store.delete_project(project_id)
    return {"status": "deleted", "id": project_id}


async def init_project_cody_md(project_id: str, store: ProjectStore):
    """Generate CODY.md for a project using AI analysis (like `cody init`)."""
    logger.info("Init CODY.md: project=%s", project_id)
    project = store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

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
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate CODY.md: {e}",
        )
