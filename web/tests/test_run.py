"""Tests for /run and /run/stream endpoints — migrated from test_server.py."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from cody.core.runner import CodyResult, TextDeltaEvent, DoneEvent
from cody.core.session import SessionStore
from web.backend.app import app


def _mock_cody_result(output, input_tokens=10, output_tokens=5):
    """Create a CodyResult for testing."""
    mock_usage = MagicMock()
    mock_usage.input_tokens = input_tokens
    mock_usage.output_tokens = output_tokens
    mock_usage.total_tokens = input_tokens + output_tokens
    mock_raw = MagicMock()
    mock_raw.usage.return_value = mock_usage
    mock_raw.all_messages.return_value = []
    return CodyResult(output=output, _raw_result=mock_raw)


# ── POST /run ────────────────────────────────────────────────────────────────


def test_run_agent():
    """POST /run executes agent and returns result."""
    mock_result = _mock_cody_result("I created the file.", input_tokens=100, output_tokens=50)

    with patch("web.backend.routes.run.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = AsyncMock(return_value=mock_result)

        client = TestClient(app)
        resp = client.post("/run", json={"prompt": "create hello.py"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["output"] == "I created the file."
    assert data["usage"]["input_tokens"] == 100
    assert data["usage"]["output_tokens"] == 50
    assert data["usage"]["total_tokens"] == 150


def test_run_agent_error():
    """POST /run returns 500 on agent failure."""
    with patch("web.backend.routes.run.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = AsyncMock(side_effect=RuntimeError("LLM API error"))

        client = TestClient(app)
        resp = client.post("/run", json={"prompt": "test"})

    assert resp.status_code == 500
    data = resp.json()
    assert data["error"]["code"] == "SERVER_ERROR"
    assert "LLM API error" in data["error"]["message"]


def test_run_missing_prompt():
    """POST /run without prompt should fail validation."""
    client = TestClient(app)
    resp = client.post("/run", json={})
    assert resp.status_code == 422


def test_run_with_session_id(tmp_path):
    """POST /run with session_id uses session-aware run."""
    store = SessionStore(db_path=tmp_path / "test.db")
    session = store.create_session(title="test")

    mock_result = _mock_cody_result("done with session")

    with patch("web.backend.routes.run.AgentRunner") as MockRunner, \
         patch("web.backend.routes.run.get_session_store", return_value=store):
        instance = MockRunner.return_value
        instance.run_with_session = AsyncMock(return_value=(mock_result, session.id))

        client = TestClient(app)
        resp = client.post("/run", json={
            "prompt": "hello",
            "session_id": session.id,
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["output"] == "done with session"
    assert data["session_id"] == session.id
    instance.run_with_session.assert_called_once()


def test_run_without_session_id():
    """POST /run without session_id uses plain run."""
    mock_result = _mock_cody_result("no session")

    with patch("web.backend.routes.run.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = AsyncMock(return_value=mock_result)

        client = TestClient(app)
        resp = client.post("/run", json={"prompt": "hello"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] is None


# ── POST /run/stream ─────────────────────────────────────────────────────────


def test_run_stream():
    """POST /run/stream returns SSE stream with structured events."""
    async def fake_stream(prompt, message_history=None):
        yield TextDeltaEvent(content="Hello")
        yield TextDeltaEvent(content=" World")
        yield DoneEvent(result=CodyResult(output="Hello World"))

    with patch("web.backend.routes.run.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run_stream = fake_stream

        client = TestClient(app)
        resp = client.post("/run/stream", json={"prompt": "test"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    assert '"type": "text_delta"' in body
    assert "Hello" in body
    assert "World" in body
    assert '"type": "done"' in body


def test_run_stream_error():
    """POST /run/stream handles errors in SSE."""
    async def failing_stream(prompt, message_history=None):
        raise RuntimeError("stream broke")
        yield  # noqa: F841 — make it a generator

    with patch("web.backend.routes.run.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run_stream = failing_stream

        client = TestClient(app)
        resp = client.post("/run/stream", json={"prompt": "test"})

    assert resp.status_code == 200
    assert '"type": "error"' in resp.text
    assert "stream broke" in resp.text
