"""Run endpoints — POST /run and POST /run/stream.

Migrated from cody/server.py. Uses core AgentRunner directly.
"""

import json
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from cody.core import AgentRunner
from cody.core.errors import (
    CodyAPIError, ErrorCode,
    ToolError, ToolPermissionDenied, ToolPathDenied,
)

from ..helpers import config_from_run_request, raise_structured, serialize_stream_event
from ..models import RunRequest, RunResponse, ToolTraceResponse
from ..state import get_session_store

router = APIRouter(tags=["run"])


@router.post("/run", response_model=RunResponse)
async def run_agent(request: RunRequest):
    """Run agent with prompt, optionally within a session."""
    try:
        config = config_from_run_request(request)
        workdir = Path(request.workdir) if request.workdir else Path.cwd()
        extra_roots = [Path(r) for r in (request.allowed_roots or [])]
        runner = AgentRunner(config=config, workdir=workdir, extra_roots=extra_roots)

        if request.session_id is not None:
            store = get_session_store()
            result, sid = await runner.run_with_session(
                request.prompt, store, request.session_id
            )
        else:
            result = await runner.run(request.prompt)
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

        return RunResponse(
            output=result.output,
            thinking=result.thinking,
            tool_traces=traces,
            session_id=sid,
            usage=usage_data,
        )

    except (ToolPermissionDenied, ToolPathDenied) as e:
        raise_structured(e.code, e.message, status_code=403)
    except ToolError as e:
        raise_structured(e.code, e.message, status_code=400)
    except ValueError as e:
        msg = str(e)
        if "Session not found" in msg:
            raise_structured(ErrorCode.SESSION_NOT_FOUND, msg, status_code=404)
        else:
            raise_structured(ErrorCode.INVALID_PARAMS, msg, status_code=400)
    except CodyAPIError:
        raise
    except Exception as e:
        raise_structured(ErrorCode.SERVER_ERROR, str(e), status_code=500)


@router.post("/run/stream")
async def run_agent_stream(request: RunRequest):
    """Run agent with streaming response, emitting structured events."""

    async def generate() -> AsyncIterator[str]:
        try:
            config = config_from_run_request(request)
            workdir = Path(request.workdir) if request.workdir else Path.cwd()
            extra_roots = [Path(r) for r in (request.allowed_roots or [])]
            runner = AgentRunner(
                config=config, workdir=workdir, extra_roots=extra_roots
            )

            if request.session_id is not None:
                store = get_session_store()
                async for event, sid in runner.run_stream_with_session(
                    request.prompt, store, request.session_id
                ):
                    yield f"data: {json.dumps(serialize_stream_event(event, session_id=sid))}\n\n"
            else:
                async for event in runner.run_stream(request.prompt):
                    yield f"data: {json.dumps(serialize_stream_event(event))}\n\n"

        except Exception as e:
            error_payload = {
                "type": "error",
                "error": {
                    "code": ErrorCode.SERVER_ERROR.value,
                    "message": str(e),
                },
            }
            yield f"data: {json.dumps(error_payload)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
