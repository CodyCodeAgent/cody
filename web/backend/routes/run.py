"""Run endpoints — POST /run and POST /run/stream.

Migrated from cody/server.py. Uses core AgentRunner directly.
"""

import json
import logging
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from cody.core import AgentRunner, SessionStore
from cody.core.errors import (
    CodyAPIError, ErrorCode,
    ToolError, ToolPermissionDenied, ToolPathDenied,
)

from ..helpers import build_prompt, config_from_run_request, raise_structured, serialize_stream_event
from ..models import RunRequest, RunResponse, ToolTraceResponse
from ..state import session_store_dep
from .metrics import record_run

logger = logging.getLogger("cody.web.run")

router = APIRouter(tags=["run"])


@router.post("/run", response_model=RunResponse)
async def run_agent(
    request: RunRequest,
    store: SessionStore = Depends(session_store_dep),
):
    """Run agent with prompt, optionally within a session."""
    logger.info(
        "POST /run: session=%s prompt_len=%d workdir=%s",
        request.session_id, len(request.prompt), request.workdir or "(cwd)",
    )
    try:
        config = config_from_run_request(request)

        # Fail early if config is incomplete
        if not config.is_ready():
            missing = config.missing_fields()
            raise_structured(
                ErrorCode.INVALID_PARAMS,
                f"Configuration incomplete: {', '.join(missing)}",
                status_code=422,
            )

        workdir = Path(request.workdir) if request.workdir else Path.cwd()
        extra_roots = [Path(r) for r in (request.allowed_roots or [])]
        runner = AgentRunner(config=config, workdir=workdir, extra_roots=extra_roots)

        images_raw = [img.model_dump() for img in request.images] if request.images else None
        prompt = build_prompt(request.prompt, images_raw)

        inc_tools = request.include_tools
        exc_tools = request.exclude_tools

        if request.session_id is not None:
            result, sid = await runner.run_with_session(
                prompt, store, request.session_id,
                include_tools=inc_tools, exclude_tools=exc_tools,
            )
        else:
            result = await runner.run(
                prompt, include_tools=inc_tools, exclude_tools=exc_tools,
            )
            sid = None

        traces = None
        if result.tool_traces:
            traces = [
                ToolTraceResponse(
                    tool_name=t.tool_name,
                    args=t.args,
                    result=t.result[:500] if t.result else "",
                )
                for t in result.tool_traces
            ]

        usage_data = None
        usage = result.usage()
        if usage:
            usage_data = {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
            }

        logger.info(
            "POST /run done: output_len=%d traces=%d tokens=%s",
            len(result.output or ""),
            len(result.tool_traces or []),
            usage_data.get("total_tokens") if usage_data else "N/A",
        )

        # Record metrics
        if usage_data:
            record_run(
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )

        return RunResponse(
            output=result.output,
            thinking=result.thinking,
            tool_traces=traces,
            session_id=sid,
            usage=usage_data,
        )

    except (ToolPermissionDenied, ToolPathDenied) as e:
        logger.warning("POST /run permission denied: %s", e.message)
        raise_structured(e.code, e.message, status_code=403)
    except ToolError as e:
        logger.warning("POST /run tool error: %s", e.message)
        raise_structured(e.code, e.message, status_code=400)
    except ValueError as e:
        msg = str(e)
        logger.warning("POST /run value error: %s", msg)
        if "Session not found" in msg:
            raise_structured(ErrorCode.SESSION_NOT_FOUND, msg, status_code=404)
        else:
            raise_structured(ErrorCode.INVALID_PARAMS, msg, status_code=400)
    except CodyAPIError:
        raise
    except Exception as e:
        logger.error("POST /run unexpected error: %s", e, exc_info=True)
        raise_structured(ErrorCode.SERVER_ERROR, str(e), status_code=500)


@router.post("/run/stream")
async def run_agent_stream(
    request: RunRequest,
    store: SessionStore = Depends(session_store_dep),
):
    """Run agent with streaming response, emitting structured events."""
    logger.info(
        "POST /run/stream: session=%s prompt_len=%d workdir=%s",
        request.session_id, len(request.prompt), request.workdir or "(cwd)",
    )

    async def generate() -> AsyncIterator[str]:
        try:
            config = config_from_run_request(request)

            # Fail early if config is incomplete
            if not config.is_ready():
                missing = config.missing_fields()
                error_payload = {
                    "type": "error",
                    "error": {
                        "code": ErrorCode.INVALID_PARAMS.value,
                        "message": f"Configuration incomplete: {', '.join(missing)}",
                    },
                }
                yield f"data: {json.dumps(error_payload)}\n\n"
                return

            workdir = Path(request.workdir) if request.workdir else Path.cwd()
            extra_roots = [Path(r) for r in (request.allowed_roots or [])]
            runner = AgentRunner(
                config=config, workdir=workdir, extra_roots=extra_roots
            )

            images_raw = [img.model_dump() for img in request.images] if request.images else None
            prompt = build_prompt(request.prompt, images_raw)

            inc_tools = request.include_tools
            exc_tools = request.exclude_tools

            if request.session_id is not None:
                async for event, sid in runner.run_stream_with_session(
                    prompt, store, request.session_id,
                    include_tools=inc_tools, exclude_tools=exc_tools,
                ):
                    yield f"data: {json.dumps(serialize_stream_event(event, session_id=sid))}\n\n"
            else:
                async for event in runner.run_stream(
                    prompt, include_tools=inc_tools, exclude_tools=exc_tools,
                ):
                    yield f"data: {json.dumps(serialize_stream_event(event))}\n\n"

        except Exception as e:
            logger.error("POST /run/stream error: %s", e, exc_info=True)
            error_payload = {
                "type": "error",
                "error": {
                    "code": ErrorCode.SERVER_ERROR.value,
                    "message": str(e),
                },
            }
            yield f"data: {json.dumps(error_payload)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
