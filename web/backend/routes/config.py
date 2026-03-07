"""Config endpoints — GET /config, PUT /config.

Allows the web UI to view and modify cody configuration,
matching CLI `cody config show` and `cody config set`.
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from cody.core import Config
from cody.core.errors import CodyAPIError, ErrorCode

from ..helpers import raise_structured

logger = logging.getLogger("cody.web.config")

router = APIRouter(tags=["config"])


class ConfigUpdateRequest(BaseModel):
    """Fields that can be updated via the web UI."""
    model: Optional[str] = None
    model_base_url: Optional[str] = None
    model_api_key: Optional[str] = None
    enable_thinking: Optional[bool] = None
    thinking_budget: Optional[int] = None


@router.get("/config/status")
async def get_config_status(workdir: Optional[str] = None):
    """Return config readiness status and missing fields."""
    try:
        wd = Path(workdir) if workdir else Path.cwd()
        cfg = Config.load(workdir=wd)
        return {
            "is_ready": cfg.is_ready(),
            "missing_fields": cfg.missing_fields(),
        }
    except Exception as e:
        logger.error("GET /config/status error: %s", e, exc_info=True)
        raise_structured(ErrorCode.SERVER_ERROR, str(e), status_code=500)


@router.get("/config")
async def get_config(workdir: Optional[str] = None):
    """Return current configuration (excluding secrets)."""
    logger.info("GET /config workdir=%s", workdir or "(cwd)")
    try:
        wd = Path(workdir) if workdir else Path.cwd()
        cfg = Config.load(workdir=wd)
        data = cfg.model_dump(exclude_none=True)
        # Strip secrets from response
        if "model_api_key" in data:
            key = data["model_api_key"]
            data["model_api_key"] = "***" if key else ""
        if "auth" in data:
            data["auth"].pop("api_key", None)
            data["auth"].pop("token", None)
            data["auth"].pop("refresh_token", None)
        return data

    except CodyAPIError:
        raise
    except Exception as e:
        logger.error("GET /config error: %s", e, exc_info=True)
        raise_structured(ErrorCode.SERVER_ERROR, str(e), status_code=500)


@router.put("/config")
async def update_config(
    body: ConfigUpdateRequest,
    workdir: Optional[str] = None,
):
    """Update configuration and persist to config file."""
    logger.info(
        "PUT /config: model=%s thinking=%s budget=%s",
        body.model, body.enable_thinking, body.thinking_budget,
    )
    try:
        wd = Path(workdir) if workdir else Path.cwd()
        cfg = Config.load(workdir=wd)

        cfg.apply_overrides(
            model=body.model,
            enable_thinking=body.enable_thinking,
            thinking_budget=body.thinking_budget,
            model_base_url=body.model_base_url,
            model_api_key=body.model_api_key,
        )

        config_path = wd / ".cody" / "config.json"
        if not config_path.exists():
            config_path = Path.home() / ".cody" / "config.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)

        cfg.save(config_path)
        logger.info("Config saved to %s", config_path)
        return {"status": "updated"}

    except CodyAPIError:
        raise
    except Exception as e:
        logger.error("PUT /config error: %s", e, exc_info=True)
        raise_structured(ErrorCode.SERVER_ERROR, str(e), status_code=500)
