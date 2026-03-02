"""Tests for WebSocket chat proxy."""

import json


def test_chat_project_not_found(test_client):
    """WS /ws/chat/:id sends error for nonexistent project"""
    with test_client.websocket_connect("/ws/chat/nonexistent") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "not found" in msg["message"].lower()


def test_chat_ping_pong(test_client, project_store):
    """WS /ws/chat/:id responds to ping with pong"""
    p = project_store.create_project(name="Test", workdir="/tmp")

    with test_client.websocket_connect(f"/ws/chat/{p.id}") as ws:
        ws.send_text(json.dumps({"type": "ping"}))
        msg = ws.receive_json()
        assert msg["type"] == "pong"
