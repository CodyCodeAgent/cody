"""WebSocket chat proxy — relays messages between frontend and core engine.

Uses core AgentRunner directly (no HTTP SDK). This is a plain async function
called by app.py with injected dependencies.
"""

import json
import logging
from pathlib import Path

from fastapi import WebSocket, WebSocketDisconnect

from cody.core import AgentRunner

from ..db import ProjectStore
from ..helpers import serialize_stream_event
from ..state import get_config, get_session_store

logger = logging.getLogger("cody.web.chat")


async def chat_websocket(
    ws: WebSocket,
    project_id: str,
    store: ProjectStore = None,
):
    """WebSocket endpoint that streams AI responses for a project."""
    await ws.accept()
    logger.info("Chat WS connected: project=%s", project_id)

    project = store.get_project(project_id) if store else None
    if project is None:
        logger.warning("Chat WS project not found: %s", project_id)
        await ws.send_json({"type": "error", "message": "Project not found"})
        await ws.close()
        return

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type", "")

            if msg_type == "ping":
                await ws.send_json({"type": "pong"})

            elif msg_type == "message":
                prompt = data.get("content", "")
                if not prompt:
                    continue

                logger.info(
                    "Chat message: project=%s session=%s prompt_len=%d",
                    project_id, project.session_id, len(prompt),
                )

                try:
                    workdir = Path(project.workdir)
                    config = get_config(workdir)

                    # Apply per-message model/thinking overrides from frontend
                    config.apply_overrides(
                        model=data.get("model"),
                        enable_thinking=data.get("enable_thinking"),
                        thinking_budget=data.get("thinking_budget"),
                    )
                    if data.get("model"):
                        logger.info("Chat override: model=%s", data["model"])

                    runner = AgentRunner(config=config, workdir=workdir)
                    session_store = get_session_store()

                    event_count = 0
                    if project.session_id:
                        async for event, sid in runner.run_stream_with_session(
                            prompt, session_store, project.session_id
                        ):
                            payload = serialize_stream_event(event, session_id=sid)
                            await ws.send_json(payload)
                            event_count += 1
                    else:
                        async for event in runner.run_stream(prompt):
                            payload = serialize_stream_event(event)
                            await ws.send_json(payload)
                            event_count += 1

                    logger.info(
                        "Chat stream done: project=%s events=%d",
                        project_id, event_count,
                    )
                except Exception as e:
                    logger.error(
                        "Chat error: project=%s error=%s", project_id, e,
                        exc_info=True,
                    )
                    await ws.send_json({
                        "type": "error",
                        "message": str(e),
                    })

    except WebSocketDisconnect:
        logger.info("Chat WS disconnected: project=%s", project_id)
    except Exception as e:
        logger.error(
            "Chat WS unexpected error: project=%s error=%s",
            project_id, e, exc_info=True,
        )
