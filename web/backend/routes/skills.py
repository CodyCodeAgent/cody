"""Skills endpoints — GET /skills, GET /skills/{name}.

Migrated from cody/server.py.
"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter

from cody.core.errors import CodyAPIError, ErrorCode

from ..helpers import raise_structured
from ..state import get_config, get_skill_manager

router = APIRouter(tags=["skills"])


@router.get("/skills")
async def list_skills(workdir: Optional[str] = None):
    """List all available skills."""
    try:
        wd = Path(workdir) if workdir else Path.cwd()
        config = get_config(wd)
        sm = get_skill_manager(config, wd)
        skills = sm.list_skills()

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
        raise_structured(ErrorCode.SERVER_ERROR, str(e), status_code=500)


@router.get("/skills/{skill_name}")
async def get_skill(skill_name: str, workdir: Optional[str] = None):
    """Get skill documentation."""
    try:
        wd = Path(workdir) if workdir else Path.cwd()
        config = get_config(wd)
        sm = get_skill_manager(config, wd)
        skill = sm.get_skill(skill_name)
        if not skill:
            raise_structured(
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
        raise_structured(ErrorCode.SERVER_ERROR, str(e), status_code=500)
