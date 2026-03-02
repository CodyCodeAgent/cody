"""Project CRUD business logic.

These are plain async functions called by app.py with injected dependencies.
They are NOT decorated with @router — FastAPI registration happens in app.py.
"""

from pathlib import Path

from fastapi import HTTPException

from ..db import ProjectStore
from ..models import ProjectCreate, ProjectUpdate, ProjectResponse


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
    return [_project_response(p) for p in projects]


async def create_project(body: ProjectCreate, store: ProjectStore,
                         cody_client=None):
    """Create a new project.

    Initializes .cody/ in workdir and creates a linked cody session.
    """
    workdir = Path(body.workdir)
    if not workdir.is_dir():
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

    # Create a cody session via SDK
    if cody_client is not None:
        try:
            session = await cody_client.create_session(
                title=body.name, workdir=str(workdir)
            )
            store.set_session_id(project.id, session.id)
            project = store.get_project(project.id)
        except Exception:
            # Core server may be unavailable; project still created
            pass

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


async def delete_project(project_id: str, store: ProjectStore,
                         cody_client=None):
    """Delete a project."""
    project = store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Try to delete linked cody session
    if cody_client is not None and project.session_id:
        try:
            await cody_client.delete_session(project.session_id)
        except Exception:
            pass

    store.delete_project(project_id)
    return {"status": "deleted", "id": project_id}
