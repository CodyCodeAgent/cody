"""Skills endpoints — list, detail, enable, disable.

Migrated from cody/server.py with enable/disable additions.
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter

from cody.core.errors import CodyAPIError, ErrorCode

from ..helpers import raise_structured
from ..state import get_config, get_skill_manager

logger = logging.getLogger("cody.web.skills")

router = APIRouter(tags=["skills"])


@router.get("/skills")
async def list_skills(workdir: Optional[str] = None):
    """List all available skills."""
    logger.info("GET /skills workdir=%s", workdir or "(cwd)")
    try:
        wd = Path(workdir) if workdir else Path.cwd()
        config = get_config(wd)
        sm = get_skill_manager(config, wd)
        skills = sm.list_skills()
        logger.info("Listed %d skills", len(skills))

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
        logger.error("GET /skills error: %s", e, exc_info=True)
        raise_structured(ErrorCode.SERVER_ERROR, str(e), status_code=500)


@router.get("/skills/{skill_name}")
async def get_skill(skill_name: str, workdir: Optional[str] = None):
    """Get skill documentation."""
    logger.info("GET /skills/%s", skill_name)
    try:
        wd = Path(workdir) if workdir else Path.cwd()
        config = get_config(wd)
        sm = get_skill_manager(config, wd)
        skill = sm.get_skill(skill_name)
        if not skill:
            logger.warning("Skill not found: %s", skill_name)
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
        logger.error("GET /skills/%s error: %s", skill_name, e, exc_info=True)
        raise_structured(ErrorCode.SERVER_ERROR, str(e), status_code=500)


@router.post("/skills/{skill_name}/enable")
async def enable_skill(skill_name: str, workdir: Optional[str] = None):
    """Enable a skill and persist to config."""
    logger.info("POST /skills/%s/enable", skill_name)
    try:
        wd = Path(workdir) if workdir else Path.cwd()
        config = get_config(wd)
        sm = get_skill_manager(config, wd)

        skill = sm.get_skill(skill_name)
        if not skill:
            logger.warning("Enable failed — skill not found: %s", skill_name)
            raise_structured(
                ErrorCode.SKILL_NOT_FOUND,
                f"Skill not found: {skill_name}",
                status_code=404,
            )

        sm.enable_skill(skill_name)

        # Persist to config file (same logic as CLI)
        config_path = wd / ".cody" / "config.json"
        if not config_path.exists():
            config_path = Path.home() / ".cody" / "config.json"
        config.save(config_path)
        logger.info("Skill enabled: %s (saved to %s)", skill_name, config_path)

        return {"name": skill_name, "enabled": True}

    except CodyAPIError:
        raise
    except Exception as e:
        logger.error("Enable skill %s error: %s", skill_name, e, exc_info=True)
        raise_structured(ErrorCode.SERVER_ERROR, str(e), status_code=500)


@router.post("/skills/{skill_name}/disable")
async def disable_skill(skill_name: str, workdir: Optional[str] = None):
    """Disable a skill and persist to config."""
    logger.info("POST /skills/%s/disable", skill_name)
    try:
        wd = Path(workdir) if workdir else Path.cwd()
        config = get_config(wd)
        sm = get_skill_manager(config, wd)

        skill = sm.get_skill(skill_name)
        if not skill:
            logger.warning("Disable failed — skill not found: %s", skill_name)
            raise_structured(
                ErrorCode.SKILL_NOT_FOUND,
                f"Skill not found: {skill_name}",
                status_code=404,
            )

        sm.disable_skill(skill_name)

        config_path = wd / ".cody" / "config.json"
        if not config_path.exists():
            config_path = Path.home() / ".cody" / "config.json"
        config.save(config_path)
        logger.info("Skill disabled: %s (saved to %s)", skill_name, config_path)

        return {"name": skill_name, "enabled": False}

    except CodyAPIError:
        raise
    except Exception as e:
        logger.error("Disable skill %s error: %s", skill_name, e, exc_info=True)
        raise_structured(ErrorCode.SERVER_ERROR, str(e), status_code=500)
