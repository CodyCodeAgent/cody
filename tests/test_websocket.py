"""Tests for WebSocket API"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from cody.server import app


# ── Basic WebSocket protocol ────────────────────────────────────────────────


def test_ws_ping_pong():
    """WebSocket ping/pong"""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "ping"})
        data = ws.receive_json()
        assert data["type"] == "pong"


def test_ws_unknown_message():
    """Unknown message type returns error"""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "unknown_thing"})
        data = ws.receive_json()
        assert data["type"] == "error"
        assert data["error"]["code"] == "INVALID_PARAMS"
        assert "unknown_thing" in data["error"]["message"].lower()


# ── Run via WebSocket ───────────────────────────────────────────────────────


def test_ws_run_missing_prompt():
    """Run without prompt returns error"""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "run", "data": {}})
        data = ws.receive_json()
        assert data["type"] == "error"
        assert data["error"]["code"] == "INVALID_PARAMS"
        assert "prompt" in data["error"]["message"]


def test_ws_run_stream():
    """Run via WebSocket with streaming"""
    async def fake_stream(prompt, message_history=None):
        for chunk in ["Hello", " WS"]:
            yield chunk

    with patch("cody.server.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run_stream = fake_stream

        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({
                "type": "run",
                "data": {"prompt": "test ws"},
            })

            # Should receive: start, text, text, done
            events = []
            for _ in range(4):
                events.append(ws.receive_json())

            types = [e["type"] for e in events]
            assert "start" in types
            assert "text" in types
            assert "done" in types

            # Check text chunks
            text_events = [e for e in events if e["type"] == "text"]
            contents = [e["content"] for e in text_events]
            assert "Hello" in contents
            assert " WS" in contents


def test_ws_run_error():
    """Run via WebSocket handles errors"""
    async def failing_stream(prompt, message_history=None):
        raise RuntimeError("ws error")
        yield

    with patch("cody.server.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run_stream = failing_stream

        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            ws.send_json({
                "type": "run",
                "data": {"prompt": "test"},
            })

            # Start event
            start = ws.receive_json()
            assert start["type"] == "start"

            # Error event
            error = ws.receive_json()
            assert error["type"] == "error"
            assert "ws error" in error["error"]["message"]


# ── Cancel ──────────────────────────────────────────────────────────────────


def test_ws_cancel_without_running():
    """Cancel when nothing is running"""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "cancel"})
        data = ws.receive_json()
        assert data["type"] == "cancelled"


# ── Multiple messages ───────────────────────────────────────────────────────


def test_ws_multiple_pings():
    """Multiple ping/pong in same connection"""
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        for _ in range(3):
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"
