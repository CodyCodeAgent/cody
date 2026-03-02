"""WebSocket chat proxy — relays messages between frontend and core via SDK.

This is a plain async function called by app.py with injected dependencies.
It is NOT decorated with @router — FastAPI registration happens in app.py.
"""

import json

from fastapi import WebSocket, WebSocketDisconnect

from ..db import ProjectStore


async def chat_websocket(
    ws: WebSocket,
    project_id: str,
    store: ProjectStore = None,
    cody_client=None,
):
    """WebSocket endpoint that proxies chat to the core server via CodyClient."""
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

                if cody_client is None:
                    await ws.send_json({
                        "type": "error",
                        "message": "Core server not configured",
                    })
                    continue

                try:
                    async for chunk in cody_client.stream(
                        prompt,
                        session_id=project.session_id,
                        workdir=project.workdir,
                    ):
                        await ws.send_json({
                            "type": chunk.type,
                            "content": chunk.content,
                            "session_id": chunk.session_id,
                        })
                except Exception as e:
                    await ws.send_json({
                        "type": "error",
                        "message": str(e),
                    })

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
