"""Task CRUD and branch management for development tasks.

Each task represents a development task under a project, with its own
git branch and chat session.
"""

import asyncio
import logging
import subprocess
from pathlib import Path

from cody.core.errors import ErrorCode

from ..db import ProjectStore
from ..helpers import raise_structured
from ..models import TaskCreate, TaskUpdate, TaskResponse
from ..state import get_session_store

logger = logging.getLogger("cody.web.tasks")


def _task_response(t) -> TaskResponse:
    return TaskResponse(
        id=t.id,
        project_id=t.project_id,
        name=t.name,
        branch_name=t.branch_name,
        session_id=t.session_id,
        status=t.status,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


async def list_tasks(project_id: str, store: ProjectStore):
    """List all tasks for a project."""
    project = await asyncio.to_thread(store.get_project, project_id)
    if project is None:
        raise_structured(ErrorCode.NOT_FOUND, "Project not found", status_code=404)
    tasks = await asyncio.to_thread(store.list_tasks, project_id)
    logger.info("List tasks: project=%s count=%d", project_id, len(tasks))
    return [_task_response(t) for t in tasks]


async def create_task(project_id: str, body: TaskCreate, store: ProjectStore):
    """Create a development task: create git branch and chat session."""
    logger.info(
        "Create task: project=%s name=%s branch=%s",
        project_id, body.name, body.branch_name,
    )
    project = await asyncio.to_thread(store.get_project, project_id)
    if project is None:
        raise_structured(ErrorCode.NOT_FOUND, "Project not found", status_code=404)

    workdir = Path(project.workdir)
    if not workdir.is_dir():
        raise_structured(
            ErrorCode.NOT_FOUND,
            f"Project directory not found: {workdir}",
            status_code=404,
        )

    # Create git branch from master/main
    branch_name = body.branch_name.strip()
    if not branch_name:
        raise_structured(
            ErrorCode.INVALID_PARAMS,
            "Branch name is required",
            status_code=400,
        )

    try:
        # Detect default branch (master or main)
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "rev-parse", "--verify", "master"],
            cwd=str(workdir),
            capture_output=True,
            text=True,
        )
        base_branch = "master" if result.returncode == 0 else "main"

        # Fetch latest
        await asyncio.to_thread(
            subprocess.run,
            ["git", "fetch", "origin", base_branch],
            cwd=str(workdir),
            capture_output=True,
            text=True,
        )

        # Create and checkout the new branch
        result = await asyncio.to_thread(
            subprocess.run,
            ["git", "checkout", "-b", branch_name, f"origin/{base_branch}"],
            cwd=str(workdir),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Branch may already exist, try to just checkout
            result2 = await asyncio.to_thread(
                subprocess.run,
                ["git", "checkout", branch_name],
                cwd=str(workdir),
                capture_output=True,
                text=True,
            )
            if result2.returncode != 0:
                raise_structured(
                    ErrorCode.SERVER_ERROR,
                    f"Failed to create/checkout branch: {result.stderr.strip() or result2.stderr.strip()}",
                    status_code=500,
                )

        logger.info("Git branch created: %s from %s", branch_name, base_branch)
    except FileNotFoundError:
        logger.warning("Git not found, skipping branch creation")
    except Exception as e:
        if hasattr(e, 'status_code'):
            raise
        logger.warning("Git branch creation failed: %s", e)

    # Create task in DB
    task = await asyncio.to_thread(
        store.create_task,
        project_id=project_id,
        name=body.name,
        branch_name=branch_name,
    )

    # Create a chat session for this task
    try:
        session_store = get_session_store()
        session = await asyncio.to_thread(
            session_store.create_session,
            title=f"{project.name} - {body.name}",
            workdir=str(workdir),
        )
        await asyncio.to_thread(store.set_task_session_id, task.id, session.id)
        task = await asyncio.to_thread(store.get_task, task.id)
        logger.info("Task created: id=%s session=%s", task.id, session.id)
    except Exception as e:
        logger.warning("Session creation failed for task %s: %s", task.id, e)

    return _task_response(task)


async def get_task(task_id: str, store: ProjectStore):
    """Get a task by ID."""
    task = await asyncio.to_thread(store.get_task, task_id)
    if task is None:
        raise_structured(ErrorCode.NOT_FOUND, "Task not found", status_code=404)
    return _task_response(task)


async def update_task(task_id: str, body: TaskUpdate, store: ProjectStore):
    """Update a task."""
    task = await asyncio.to_thread(
        store.update_task, task_id, name=body.name, status=body.status,
    )
    if task is None:
        raise_structured(ErrorCode.NOT_FOUND, "Task not found", status_code=404)
    return _task_response(task)


async def delete_task(task_id: str, store: ProjectStore):
    """Delete a task and its linked session."""
    logger.info("Delete task: id=%s", task_id)
    task = await asyncio.to_thread(store.get_task, task_id)
    if task is None:
        raise_structured(ErrorCode.NOT_FOUND, "Task not found", status_code=404)

    if task.session_id:
        try:
            session_store = get_session_store()
            await asyncio.to_thread(
                session_store.delete_session, task.session_id,
            )
            logger.info("Deleted linked session: %s", task.session_id)
        except Exception as e:
            logger.warning("Failed to delete session %s: %s", task.session_id, e)

    await asyncio.to_thread(store.delete_task, task_id)
    return {"status": "deleted", "id": task_id}
