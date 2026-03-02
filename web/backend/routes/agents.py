"""Sub-agent endpoints — spawn, status, kill.

Migrated from cody/server.py.
"""

from pathlib import Path

from fastapi import APIRouter

from cody.core.errors import CodyAPIError, ErrorCode

from ..helpers import raise_structured
from ..models import SpawnRequest
from ..state import get_sub_agent_manager

router = APIRouter(tags=["agents"])


@router.post("/agent/spawn")
async def spawn_agent(request: SpawnRequest):
    """Spawn a sub-agent."""
    try:
        wd = Path(request.workdir) if request.workdir else Path.cwd()
        manager = await get_sub_agent_manager(workdir=wd)
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
        raise_structured(
            ErrorCode.AGENT_LIMIT_REACHED, str(e), status_code=429
        )
    except CodyAPIError:
        raise
    except Exception as e:
        raise_structured(ErrorCode.AGENT_ERROR, str(e), status_code=500)


@router.get("/agent/{agent_id}")
async def get_agent_status(agent_id: str):
    """Get sub-agent status."""
    manager = await get_sub_agent_manager(Path.cwd())
    result = manager.get_status(agent_id)
    if result is None:
        raise_structured(
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


@router.delete("/agent/{agent_id}")
async def kill_agent(agent_id: str):
    """Kill a running sub-agent."""
    manager = await get_sub_agent_manager(Path.cwd())
    result = manager.get_status(agent_id)
    if result is None:
        raise_structured(
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
