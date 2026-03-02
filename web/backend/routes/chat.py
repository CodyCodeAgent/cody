"""WebSocket chat proxy — relays messages between frontend and core engine.

Uses core AgentRunner directly (no HTTP SDK). This is a plain async function
called by app.py with injected dependencies.
"""

import json
from pathlib import Path

from fastapi import WebSocket, WebSocketDisconnect

from cody.core import AgentRunner

from ..db import ProjectStore
from ..helpers import serialize_stream_event
from ..state import get_config, get_session_store


async def chat_websocket(
    ws: WebSocket,
    project_id: str,
    store: ProjectStore = None,
):
    """WebSocket endpoint that streams AI responses for a project."""
    await ws.accept()

    project = store.get_project(project_id) if store else None
    if project is None:
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

                try:
                    workdir = Path(project.workdir)
                    config = get_config(workdir)
                    runner = AgentRunner(config=config, workdir=workdir)
                    session_store = get_session_store()

                    if project.session_id:
                        async for event, sid in runner.run_stream_with_session(
                            prompt, session_store, project.session_id
                        ):
                            payload = serialize_stream_event(event, session_id=sid)
                            await ws.send_json(payload)
                    else:
                        async for event in runner.run_stream(prompt):
                            payload = serialize_stream_event(event)
                            await ws.send_json(payload)
                except Exception as e:
                    await ws.send_json({
                        "type": "error",
                        "message": str(e),
                    })

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
