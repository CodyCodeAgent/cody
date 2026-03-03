"""WebSocket endpoint — WS /ws for raw agent interaction.

Migrated from cody/server.py. Supports run/cancel/ping.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from cody.core import AgentRunner
from cody.core.errors import ErrorCode

from ..helpers import build_prompt, serialize_stream_event
from ..state import get_config, get_session_store

logger = logging.getLogger("cody.web.ws")

router = APIRouter(tags=["websocket"])


class _WSConnection:
    """Manage a single WebSocket connection for agent interaction."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self._cancel_event: Optional[asyncio.Event] = None

    async def accept(self):
        await self.ws.accept()
        logger.info("RPC WS connected")

    async def send_event(self, event_type: str, data: Optional[dict] = None):
        payload: dict[str, Any] = {"type": event_type}
        if data:
            payload.update(data)
        await self.ws.send_json(payload)

    async def handle(self):
        """Main receive loop."""
        try:
            while True:
                raw = await self.ws.receive_json()
                msg_type = raw.get("type", "")

                if msg_type == "run":
                    await self._handle_run(raw.get("data", {}))
                elif msg_type == "cancel":
                    logger.info("RPC WS cancel requested")
                    if self._cancel_event:
                        self._cancel_event.set()
                    await self.send_event("cancelled")
                elif msg_type == "ping":
                    await self.send_event("pong")
                else:
                    logger.warning("RPC WS unknown message type: %s", msg_type)
                    await self.send_event("error", {
                        "error": {
                            "code": ErrorCode.INVALID_PARAMS.value,
                            "message": f"Unknown message type: {msg_type}",
                        }
                    })

        except WebSocketDisconnect:
            logger.info("RPC WS disconnected")

    async def _handle_run(self, data: dict):
        prompt_text = data.get("prompt", "")
        if not prompt_text:
            logger.warning("RPC WS run: empty prompt")
            await self.send_event("error", {
                "error": {
                    "code": ErrorCode.INVALID_PARAMS.value,
                    "message": "prompt is required",
                }
            })
            return

        prompt = build_prompt(prompt_text, data.get("images"))
        session_id = data.get("session_id")
        logger.info(
            "RPC WS run: session=%s prompt_len=%d workdir=%s",
            session_id, len(prompt_text), data.get("workdir", "(cwd)"),
        )

        self._cancel_event = asyncio.Event()

        try:
            workdir = Path(data["workdir"]) if data.get("workdir") else Path.cwd()
            config = get_config(workdir).apply_overrides(
                model=data.get("model"),
                model_base_url=data.get("model_base_url"),
                model_api_key=data.get("model_api_key"),
                enable_thinking=data.get("enable_thinking"),
                thinking_budget=data.get("thinking_budget"),
                extra_roots=data.get("allowed_roots"),
            )
            extra_roots = [Path(r) for r in (data.get("allowed_roots") or [])]
            runner = AgentRunner(
                config=config, workdir=workdir, extra_roots=extra_roots
            )

            await self.send_event("start", {"session_id": session_id})

            if session_id is not None:
                store = get_session_store()
                async for event, sid in runner.run_stream_with_session(
                    prompt, store, session_id
                ):
                    if self._cancel_event.is_set():
                        await self.send_event("cancelled")
                        return
                    payload = serialize_stream_event(event, session_id=sid)
                    await self.send_event(payload.pop("type"), payload)
            else:
                async for event in runner.run_stream(prompt):
                    if self._cancel_event.is_set():
                        await self.send_event("cancelled")
                        return
                    payload = serialize_stream_event(event)
                    await self.send_event(payload.pop("type"), payload)

        except Exception as e:
            logger.error("RPC WS run error: %s", e, exc_info=True)
            await self.send_event("error", {
                "error": {
                    "code": ErrorCode.SERVER_ERROR.value,
                    "message": str(e),
                }
            })

        finally:
            self._cancel_event = None


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket endpoint for real-time bidirectional interaction."""
    conn = _WSConnection(ws)
    await conn.accept()
    await conn.handle()
