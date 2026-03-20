"""WebSocket chat for development tasks.

Similar to chat.py but operates on a Task (which has its own session and
uses the project's code_paths as allowed_roots). Router registered in app.py.
"""

import asyncio
import json
import logging
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from cody.core import SessionStore
from cody.core.auth import AuthError
from cody.core.interaction import InteractionResponse

from ..db import ProjectStore
from ..helpers import build_prompt, resolve_chat_runner, serialize_stream_event
from ..middleware import validate_credential
from ..state import get_project_store, session_store_dep

logger = logging.getLogger("cody.web.task_chat")

router = APIRouter(tags=["task_chat"])


@router.websocket("/ws/chat/task/{task_id}")
async def task_chat_websocket(
    ws: WebSocket,
    task_id: str,
    store: ProjectStore = Depends(get_project_store),
    session_store: SessionStore = Depends(session_store_dep),
):
    """WebSocket endpoint that streams AI responses for a development task."""
    # Authenticate before accepting
    try:
        token = ws.query_params.get("token", "") or ws.headers.get("authorization", "")
        if token.startswith("Bearer "):
            token = token[7:]
        validate_credential(token)
    except AuthError as e:
        logger.warning("Task chat WS auth failed: task=%s reason=%s", task_id, e)
        await ws.close(code=4001, reason=str(e))
        return

    await ws.accept()
    logger.info("Task chat WS connected: task=%s", task_id)

    task = store.get_task(task_id) if store else None
    if task is None:
        logger.warning("Task chat WS task not found: %s", task_id)
        await ws.send_json({"type": "error", "message": "Task not found"})
        await ws.close()
        return

    project = store.get_project(task.project_id) if store else None
    if project is None:
        logger.warning("Task chat WS project not found: %s", task.project_id)
        await ws.send_json({"type": "error", "message": "Project not found"})
        await ws.close()
        return

    # Ensure we're on the right git branch
    workdir = Path(project.workdir)
    if workdir.is_dir():
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(workdir),
                capture_output=True,
                text=True,
            )
            current_branch = result.stdout.strip() if result.returncode == 0 else ""
            if current_branch and current_branch != task.branch_name:
                subprocess.run(
                    ["git", "checkout", task.branch_name],
                    cwd=str(workdir),
                    capture_output=True,
                    text=True,
                )
                logger.info(
                    "Switched branch: %s -> %s", current_branch, task.branch_name,
                )
        except FileNotFoundError:
            pass

    logger.info(
        "Task chat WS ready: task=%s project=%s branch=%s session=%s",
        task_id, project.name, task.branch_name, task.session_id,
    )

    active_runner = None
    stream_task = None
    send_lock = asyncio.Lock()

    async def _safe_send(payload: dict):
        async with send_lock:
            await ws.send_json(payload)

    async def _run_stream(runner, prompt, sid):
        nonlocal active_runner
        active_runner = runner
        try:
            t0 = time.monotonic()
            event_count = 0

            if sid:
                async for event, s in runner.run_stream_with_session(
                    prompt, session_store, sid
                ):
                    payload = serialize_stream_event(event, session_id=s)
                    await _safe_send(payload)
                    event_count += 1
            else:
                async for event in runner.run_stream(prompt):
                    payload = serialize_stream_event(event)
                    await _safe_send(payload)
                    event_count += 1

            elapsed = time.monotonic() - t0
            logger.info(
                "Task chat stream done: task=%s events=%d elapsed=%.1fs",
                task_id, event_count, elapsed,
            )
        except Exception as e:
            logger.error(
                "Task chat error: task=%s error=%s",
                task_id, e, exc_info=True,
            )
            err_msg = str(e)
            err_lower = err_msg.lower()
            if "401" in err_msg or "unauthorized" in err_lower:
                err_msg = "API authentication failed — please check your API key."
            elif "429" in err_msg or "rate" in err_lower:
                err_msg = "API rate limit hit — please wait and try again."
            await _safe_send({"type": "error", "message": err_msg})
        finally:
            active_runner = None

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type", "")
            logger.debug("Task chat WS recv: task=%s type=%s", task_id, msg_type)

            if msg_type == "ping":
                await _safe_send({"type": "pong"})

            elif msg_type == "submit_interaction":
                request_id = data.get("request_id", "")
                action = data.get("action", "answer")
                content = data.get("content", "")
                if active_runner and request_id:
                    response = InteractionResponse(
                        request_id=request_id,
                        action=action,
                        content=content,
                    )
                    await active_runner.submit_interaction(response)
                    logger.info(
                        "Task chat WS interaction submitted: task=%s id=%s",
                        task_id, request_id,
                    )
                else:
                    await _safe_send({
                        "type": "error",
                        "message": "No active run or missing request_id",
                    })

            elif msg_type == "message":
                prompt_text = data.get("content", "")
                if not prompt_text:
                    continue
                prompt = build_prompt(prompt_text, data.get("images"))

                logger.info(
                    "Task chat message: task=%s session=%s prompt_len=%d",
                    task_id, task.session_id, len(prompt_text),
                )

                try:
                    try:
                        config, runner = resolve_chat_runner(
                            workdir, data, project.code_paths,
                        )
                    except ValueError:
                        await _safe_send({
                            "type": "error",
                            "message": "No API key configured — please set your API key in Settings.",
                        })
                        continue

                    stream_task = asyncio.create_task(
                        _run_stream(runner, prompt, task.session_id)
                    )

                except Exception as e:
                    logger.error(
                        "Task chat setup error: task=%s error=%s",
                        task_id, e, exc_info=True,
                    )
                    await _safe_send({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        logger.info("Task chat WS disconnected: task=%s", task_id)
    except Exception as e:
        logger.error(
            "Task chat WS unexpected error: task=%s error=%s",
            task_id, e, exc_info=True,
        )
    finally:
        if stream_task and not stream_task.done():
            stream_task.cancel()
            try:
                await stream_task
            except asyncio.CancelledError:
                pass
