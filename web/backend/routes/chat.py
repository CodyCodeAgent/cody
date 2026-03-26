"""WebSocket chat proxy — relays messages between frontend and core engine.

Uses core AgentRunner directly (no HTTP SDK). Router registered in app.py.

Stream tasks survive WebSocket disconnection: if the client reconnects,
the new connection adopts the running stream.  Events emitted while no
client is connected are silently dropped (the final result is persisted
to the session store and loaded by the frontend on reconnect).
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from cody.core import SessionStore
from cody.core.auth import AuthError
from cody.core.interaction import InteractionResponse

from ..db import ProjectStore
from ..helpers import build_prompt, resolve_chat_runner, serialize_stream_event
from ..middleware import validate_credential
from ..state import get_project_store, session_store_dep

logger = logging.getLogger("cody.web.chat")

router = APIRouter(tags=["chat"])


# ── Active run registry ──────────────────────────────────────────────────────
# Keeps stream tasks alive across WebSocket reconnections.


@dataclass
class _ActiveRun:
    """Mutable state for a running stream, shared across WS connections."""
    ws: Optional[WebSocket] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    runner: object = None  # AgentRunner
    cancel_event: Optional[asyncio.Event] = None
    task: Optional[asyncio.Task] = None


# project_id → _ActiveRun
_active_runs: dict[str, _ActiveRun] = {}


async def _safe_send(run: _ActiveRun, payload: dict) -> None:
    """Send to the current WebSocket, silently swallowing errors."""
    async with run.lock:
        if run.ws is not None:
            try:
                await run.ws.send_json(payload)
            except Exception:
                pass  # client disconnected; stream keeps running


# ── WebSocket endpoint ────────────────────────────────────────────────────────


@router.websocket("/ws/chat/{project_id}")
async def chat_websocket(
    ws: WebSocket,
    project_id: str,
    store: ProjectStore = Depends(get_project_store),
    session_store: SessionStore = Depends(session_store_dep),
):
    """WebSocket endpoint that streams AI responses for a project."""
    # Authenticate before accepting
    try:
        token = ws.query_params.get("token", "") or ws.headers.get("authorization", "")
        if token.startswith("Bearer "):
            token = token[7:]
        validate_credential(token)
    except AuthError as e:
        logger.warning("Chat WS auth failed: project=%s reason=%s", project_id, e)
        await ws.close(code=4001, reason=str(e))
        return

    await ws.accept()
    logger.info("Chat WS connected: project=%s", project_id)

    project = store.get_project(project_id) if store else None
    if project is None:
        logger.warning("Chat WS project not found: %s", project_id)
        await ws.send_json({"type": "error", "message": "Project not found"})
        await ws.close()
        return

    logger.info(
        "Chat WS ready: project=%s name=%s workdir=%s session=%s",
        project_id, project.name, project.workdir, project.session_id,
    )

    # Adopt or create active-run state for this project
    run = _active_runs.get(project_id)
    if run is None:
        run = _ActiveRun()
        _active_runs[project_id] = run

    # Swap sender to this connection (previous one is dead or absent)
    run.ws = ws

    # If there's an active stream, tell the frontend
    if run.task and not run.task.done():
        logger.info("Chat WS reconnect: project=%s (active stream adopted)", project_id)
        await ws.send_json({"type": "resuming"})

    # ── stream helper ────────────────────────────────────────────────────

    async def _run_stream(
        runner, prompt, sid, *,
        include_tools=None, exclude_tools=None,
        run_cancel_event: asyncio.Event | None = None,
    ):
        run.runner = runner
        try:
            t0 = time.monotonic()
            event_count = 0
            last_event_type = ""

            if sid:
                logger.info(
                    "Chat stream start: project=%s session=%s (with session)",
                    project_id, sid,
                )
                async for event, s in runner.run_stream_with_session(
                    prompt, session_store, sid,
                    include_tools=include_tools, exclude_tools=exclude_tools,
                    cancel_event=run_cancel_event,
                ):
                    etype = type(event).__name__
                    last_event_type = etype
                    payload = serialize_stream_event(event, session_id=s)
                    await _safe_send(run, payload)
                    event_count += 1
                    if event_count <= 3 or etype == "DoneEvent":
                        logger.debug(
                            "Chat event #%d: project=%s type=%s",
                            event_count, project_id, etype,
                        )
            else:
                logger.info(
                    "Chat stream start: project=%s (no session)",
                    project_id,
                )
                async for event in runner.run_stream(
                    prompt, include_tools=include_tools, exclude_tools=exclude_tools,
                    cancel_event=run_cancel_event,
                ):
                    etype = type(event).__name__
                    last_event_type = etype
                    payload = serialize_stream_event(event)
                    await _safe_send(run, payload)
                    event_count += 1
                    if event_count <= 3 or etype == "DoneEvent":
                        logger.debug(
                            "Chat event #%d: project=%s type=%s",
                            event_count, project_id, etype,
                        )

            elapsed = time.monotonic() - t0
            logger.info(
                "Chat stream done: project=%s events=%d last=%s elapsed=%.1fs",
                project_id, event_count, last_event_type, elapsed,
            )
        except Exception as e:
            logger.error(
                "Chat error: project=%s error_type=%s error=%s",
                project_id, type(e).__name__, e,
                exc_info=True,
            )
            err_msg = str(e)
            err_type = type(e).__name__
            err_lower = err_msg.lower()
            if "401" in err_msg or "unauthorized" in err_lower or ("invalid" in err_lower and "api" in err_lower):
                err_msg = "API authentication failed — please check your API key in Settings."
            elif "402" in err_msg or "insufficient" in err_lower:
                err_msg = "API quota exceeded — please check your billing or usage limits."
            elif "429" in err_msg or "rate" in err_lower:
                err_msg = "API rate limit hit — please wait a moment and try again."
            elif "RemoteProtocolError" in err_type or "peer closed" in err_lower or "incomplete chunked" in err_lower:
                err_msg = "API connection error — the model service closed the connection unexpectedly. Please check your API key and try again."
            elif "timeout" in err_lower or "timed out" in err_lower:
                err_msg = "API request timed out — please try again."
            await _safe_send(run, {"type": "error", "message": err_msg})
        finally:
            run.runner = None
            run.cancel_event = None
            run.task = None
            # Clean up registry if no more state
            _active_runs.pop(project_id, None)

    # ── message loop ─────────────────────────────────────────────────────

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type", "")
            logger.debug("Chat WS recv: project=%s type=%s", project_id, msg_type)

            if msg_type == "ping":
                await ws.send_json({"type": "pong"})

            elif msg_type == "cancel":
                logger.info("Chat WS cancel: project=%s", project_id)
                if run.cancel_event:
                    run.cancel_event.set()
                else:
                    await ws.send_json({"type": "cancelled"})

            elif msg_type == "submit_interaction":
                request_id = data.get("request_id", "")
                action = data.get("action", "answer")
                content = data.get("content", "")
                if run.runner and request_id:
                    response = InteractionResponse(
                        request_id=request_id,
                        action=action,
                        content=content,
                    )
                    await run.runner.submit_interaction(response)
                    logger.info(
                        "Chat WS interaction submitted: project=%s id=%s action=%s",
                        project_id, request_id, action,
                    )
                else:
                    await ws.send_json({
                        "type": "error",
                        "message": "No active run or missing request_id",
                    })

            elif msg_type == "message":
                prompt_text = data.get("content", "")
                if not prompt_text:
                    logger.debug("Chat WS empty message, skipping")
                    continue
                prompt = build_prompt(prompt_text, data.get("images"))
                has_images = bool(data.get("images"))
                inc_tools = data.get("include_tools")
                exc_tools = data.get("exclude_tools")

                logger.info(
                    "Chat message: project=%s session=%s prompt_len=%d images=%s",
                    project_id, project.session_id, len(prompt_text), has_images,
                )

                try:
                    workdir = Path(project.workdir)
                    try:
                        config, runner = resolve_chat_runner(
                            workdir, data, project.code_paths,
                        )
                    except ValueError:
                        logger.warning("Chat no API key: project=%s", project_id)
                        await ws.send_json({
                            "type": "error",
                            "message": "No API key configured — please set your API key in Settings "
                                       "or via environment variable CODY_MODEL_API_KEY.",
                        })
                        continue

                    logger.info(
                        "Chat config: model=%s api_key_set=%s base_url=%s thinking=%s",
                        config.model, bool(config.model_api_key),
                        config.model_base_url or "(default)", config.enable_thinking,
                    )

                    run.cancel_event = asyncio.Event()
                    run.task = asyncio.create_task(
                        _run_stream(
                            runner, prompt, project.session_id,
                            include_tools=inc_tools, exclude_tools=exc_tools,
                            run_cancel_event=run.cancel_event,
                        )
                    )

                except Exception as e:
                    logger.error(
                        "Chat setup error: project=%s error=%s",
                        project_id, e, exc_info=True,
                    )
                    await ws.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        logger.info("Chat WS disconnected: project=%s", project_id)
    except Exception as e:
        logger.error(
            "Chat WS unexpected error: project=%s error=%s",
            project_id, e, exc_info=True,
        )
    finally:
        # Detach sender but do NOT cancel the stream task — it keeps running
        # and writes the result to the session store.
        run.ws = None
