"""Tests for RPC Server endpoints"""

from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from cody.core.config import Config
from cody.core.runner import CodyResult
from cody.server import app


def _mock_cody_result(output: str, input_tokens: int = 10, output_tokens: int = 5) -> CodyResult:
    """Create a CodyResult for testing."""
    mock_usage = MagicMock()
    mock_usage.input_tokens = input_tokens
    mock_usage.output_tokens = output_tokens
    mock_usage.total_tokens = input_tokens + output_tokens
    mock_raw = MagicMock()
    mock_raw.usage.return_value = mock_usage
    mock_raw.all_messages.return_value = []
    return CodyResult(output=output, _raw_result=mock_raw)


# ── Health endpoint ──────────────────────────────────────────────────────────


def test_health():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_health_returns_version():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.json()["version"] == "1.3.0"


# ── Tool endpoint ────────────────────────────────────────────────────────────


def test_tool_read_file(tmp_path):
    """Call read_file tool through /tool endpoint"""
    (tmp_path / "hello.txt").write_text("hello from server test")

    client = TestClient(app)
    resp = client.post("/tool", json={
        "tool": "read_file",
        "params": {"path": "hello.txt"},
        "workdir": str(tmp_path),
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "hello from server test" in data["result"]


def test_tool_write_file(tmp_path):
    """Call write_file tool through /tool endpoint"""
    client = TestClient(app)
    resp = client.post("/tool", json={
        "tool": "write_file",
        "params": {"path": "out.txt", "content": "written via server"},
        "workdir": str(tmp_path),
    })
    assert resp.status_code == 200
    assert "Written" in resp.json()["result"]
    assert (tmp_path / "out.txt").read_text() == "written via server"


def test_tool_list_directory(tmp_path):
    """Call list_directory tool through /tool endpoint"""
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.txt").write_text("")

    client = TestClient(app)
    resp = client.post("/tool", json={
        "tool": "list_directory",
        "params": {"path": "."},
        "workdir": str(tmp_path),
    })
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert "a.py" in result
    assert "b.txt" in result


def test_tool_grep(tmp_path):
    """Call grep tool through /tool endpoint"""
    (tmp_path / "code.py").write_text("def hello():\n    pass\n")

    client = TestClient(app)
    resp = client.post("/tool", json={
        "tool": "grep",
        "params": {"pattern": "def hello"},
        "workdir": str(tmp_path),
    })
    assert resp.status_code == 200
    assert "code.py:1:" in resp.json()["result"]


def test_tool_not_found():
    """Request a tool that doesn't exist"""
    client = TestClient(app)
    resp = client.post("/tool", json={
        "tool": "nonexistent_tool",
        "params": {},
    })
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "TOOL_NOT_FOUND"
    assert "not found" in data["error"]["message"].lower()


def test_tool_missing_params(tmp_path):
    """Call tool with missing required params"""
    client = TestClient(app)
    resp = client.post("/tool", json={
        "tool": "read_file",
        "params": {},
        "workdir": str(tmp_path),
    })
    # Should fail because 'path' param is missing
    assert resp.status_code == 500


def test_tool_path_traversal(tmp_path):
    """read_file allows outside workdir (read-only); write_file should block"""
    client = TestClient(app)
    # read_file allows outside workdir — returns 500 (file not found), not 403
    resp = client.post("/tool", json={
        "tool": "read_file",
        "params": {"path": "../../../etc/nonexistent_file"},
        "workdir": str(tmp_path),
    })
    assert resp.status_code == 500

    # write_file should still block path traversal
    resp = client.post("/tool", json={
        "tool": "write_file",
        "params": {"path": "../../../evil.txt", "content": "bad"},
        "workdir": str(tmp_path),
    })
    assert resp.status_code == 403
    assert "outside" in resp.json()["error"]["message"].lower()


# ── Skills endpoint ──────────────────────────────────────────────────────────


def test_skills_list():
    """GET /skills returns a list"""
    client = TestClient(app)
    resp = client.get("/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert "skills" in data
    assert isinstance(data["skills"], list)


def test_skills_list_contains_builtin():
    """Built-in git skill should appear"""
    client = TestClient(app)
    resp = client.get("/skills")
    names = [s["name"] for s in resp.json()["skills"]]
    assert "git" in names


def test_skills_list_has_expected_fields():
    """Each skill should have name, description, enabled, source"""
    client = TestClient(app)
    resp = client.get("/skills")
    for skill in resp.json()["skills"]:
        assert "name" in skill
        assert "enabled" in skill
        assert "source" in skill


def test_skill_detail():
    """GET /skills/git returns skill documentation"""
    client = TestClient(app)
    resp = client.get("/skills/git")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "git"
    assert "documentation" in data
    assert len(data["documentation"]) > 0


def test_skill_not_found():
    """GET /skills/nonexistent returns 404"""
    client = TestClient(app)
    resp = client.get("/skills/nonexistent_skill_xyz")
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "SKILL_NOT_FOUND"
    assert "not found" in data["error"]["message"].lower()


# ── Run endpoint ─────────────────────────────────────────────────────────────


def test_run_agent():
    """POST /run executes agent and returns result"""
    mock_result = _mock_cody_result("I created the file for you.", input_tokens=100, output_tokens=50)

    with patch("cody.server.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = AsyncMock(return_value=mock_result)

        client = TestClient(app)
        resp = client.post("/run", json={
            "prompt": "create hello.py",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["output"] == "I created the file for you."
    assert data["usage"]["input_tokens"] == 100
    assert data["usage"]["output_tokens"] == 50
    assert data["usage"]["total_tokens"] == 150


def test_run_agent_with_model_override():
    """POST /run respects model override"""
    mock_result = _mock_cody_result("done")

    with patch("cody.server.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = AsyncMock(return_value=mock_result)

        config = Config()
        with patch("cody.server._get_config", return_value=config):
            client = TestClient(app)
            resp = client.post("/run", json={
                "prompt": "test",
                "model": "openai:gpt-4o",
            })

    assert resp.status_code == 200
    # Verify model was overridden via apply_overrides
    assert config.model == "openai:gpt-4o"


def test_run_agent_with_workdir(tmp_path):
    """POST /run respects workdir"""
    mock_result = _mock_cody_result("done")

    with patch("cody.server.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = AsyncMock(return_value=mock_result)

        client = TestClient(app)
        resp = client.post("/run", json={
            "prompt": "test",
            "workdir": str(tmp_path),
        })

    assert resp.status_code == 200
    # Verify workdir was passed
    call_kwargs = MockRunner.call_args
    assert call_kwargs.kwargs["workdir"] == tmp_path


def test_run_agent_error():
    """POST /run returns 500 on agent failure"""
    with patch("cody.server.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = AsyncMock(side_effect=RuntimeError("LLM API error"))

        client = TestClient(app)
        resp = client.post("/run", json={
            "prompt": "test",
        })

    assert resp.status_code == 500
    data = resp.json()
    assert data["error"]["code"] == "SERVER_ERROR"
    assert "LLM API error" in data["error"]["message"]


# ── Stream endpoint ──────────────────────────────────────────────────────────


def test_run_stream():
    """POST /run/stream returns SSE stream with structured events"""
    from cody.core.runner import TextDeltaEvent, DoneEvent, CodyResult

    async def fake_stream(prompt, message_history=None):
        yield TextDeltaEvent(content="Hello")
        yield TextDeltaEvent(content=" ")
        yield TextDeltaEvent(content="World")
        yield DoneEvent(result=CodyResult(output="Hello World"))

    with patch("cody.server.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run_stream = fake_stream

        client = TestClient(app)
        resp = client.post("/run/stream", json={
            "prompt": "test",
        })

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    assert '"type": "text_delta"' in body
    assert "Hello" in body
    assert "World" in body
    assert '"type": "done"' in body


def test_run_stream_error():
    """POST /run/stream handles errors in SSE"""
    async def failing_stream(prompt, message_history=None):
        raise RuntimeError("stream broke")
        yield  # make it a generator

    with patch("cody.server.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run_stream = failing_stream

        client = TestClient(app)
        resp = client.post("/run/stream", json={
            "prompt": "test",
        })

    assert resp.status_code == 200
    assert '"type": "error"' in resp.text
    assert "stream broke" in resp.text


# ── Request validation ───────────────────────────────────────────────────────


def test_run_missing_prompt():
    """POST /run without prompt should fail validation"""
    client = TestClient(app)
    resp = client.post("/run", json={})
    assert resp.status_code == 422  # Pydantic validation error


def test_tool_missing_tool_name():
    """POST /tool without tool field should fail validation"""
    client = TestClient(app)
    resp = client.post("/tool", json={"params": {}})
    assert resp.status_code == 422


def test_tool_missing_params_field():
    """POST /tool without params field should fail validation"""
    client = TestClient(app)
    resp = client.post("/tool", json={"tool": "read_file"})
    assert resp.status_code == 422


# ── Session endpoints ────────────────────────────────────────────────────────


def test_create_session(tmp_path):
    """POST /sessions creates a new session"""
    with patch("cody.server._get_session_store") as mock_store_fn:
        from cody.core.session import SessionStore
        store = SessionStore(db_path=tmp_path / "test.db")
        mock_store_fn.return_value = store

        client = TestClient(app)
        resp = client.post("/sessions?title=my+chat&model=test-model")

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "my chat"
    assert data["model"] == "test-model"
    assert data["message_count"] == 0
    assert len(data["id"]) == 12


def test_list_sessions(tmp_path):
    """GET /sessions lists recent sessions"""
    from cody.core.session import SessionStore
    store = SessionStore(db_path=tmp_path / "test.db")
    store.create_session(title="session 1")
    store.create_session(title="session 2")

    with patch("cody.server._get_session_store", return_value=store):
        client = TestClient(app)
        resp = client.get("/sessions")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["sessions"]) == 2


def test_list_sessions_empty(tmp_path):
    """GET /sessions returns empty list when no sessions"""
    from cody.core.session import SessionStore
    store = SessionStore(db_path=tmp_path / "test.db")

    with patch("cody.server._get_session_store", return_value=store):
        client = TestClient(app)
        resp = client.get("/sessions")

    assert resp.status_code == 200
    assert resp.json()["sessions"] == []


def test_get_session_detail(tmp_path):
    """GET /sessions/:id returns session with messages"""
    from cody.core.session import SessionStore
    store = SessionStore(db_path=tmp_path / "test.db")
    session = store.create_session(title="test chat")
    store.add_message(session.id, "user", "hello")
    store.add_message(session.id, "assistant", "hi there")

    with patch("cody.server._get_session_store", return_value=store):
        client = TestClient(app)
        resp = client.get(f"/sessions/{session.id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == session.id
    assert data["title"] == "test chat"
    assert data["message_count"] == 2
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "hello"
    assert data["messages"][1]["role"] == "assistant"


def test_get_session_not_found(isolated_store, test_client):
    """GET /sessions/:id returns 404 for nonexistent session"""
    resp = test_client.get("/sessions/nonexistent_id")
    assert resp.status_code == 404


def test_delete_session(isolated_store, test_client):
    """DELETE /sessions/:id deletes session"""
    session = isolated_store.create_session(title="to delete")
    resp = test_client.delete(f"/sessions/{session.id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"
    assert isolated_store.get_session(session.id) is None


def test_delete_session_not_found(tmp_path):
    """DELETE /sessions/:id returns 404 for nonexistent session"""
    from cody.core.session import SessionStore
    store = SessionStore(db_path=tmp_path / "test.db")

    with patch("cody.server._get_session_store", return_value=store):
        client = TestClient(app)
        resp = client.delete("/sessions/nonexistent_id")

    assert resp.status_code == 404


# ── Run with session ─────────────────────────────────────────────────────────


def test_run_with_session_id(tmp_path):
    """POST /run with session_id uses session-aware run"""
    from cody.core.session import SessionStore
    store = SessionStore(db_path=tmp_path / "test.db")
    session = store.create_session(title="test")

    mock_result = _mock_cody_result("done with session")

    with patch("cody.server.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run_with_session = AsyncMock(return_value=(mock_result, session.id))

        with patch("cody.server._get_session_store", return_value=store):
            client = TestClient(app)
            resp = client.post("/run", json={
                "prompt": "hello",
                "session_id": session.id,
            })

    assert resp.status_code == 200
    data = resp.json()
    assert data["output"] == "done with session"
    assert data["session_id"] == session.id
    # Verify run_with_session was called (not plain run)
    instance.run_with_session.assert_called_once()


def test_run_without_session_id():
    """POST /run without session_id uses plain run (no session_id in response)"""
    mock_result = _mock_cody_result("no session")

    with patch("cody.server.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = AsyncMock(return_value=mock_result)

        client = TestClient(app)
        resp = client.post("/run", json={"prompt": "hello"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] is None
    instance.run.assert_called_once()
