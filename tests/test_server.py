"""Tests for RPC Server endpoints"""

from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from cody.server import app


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
    assert resp.json()["version"] == "0.1.0"


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
    assert "not found" in resp.json()["detail"].lower()


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
    """Ensure /tool endpoint respects path security"""
    client = TestClient(app)
    resp = client.post("/tool", json={
        "tool": "read_file",
        "params": {"path": "../../../etc/passwd"},
        "workdir": str(tmp_path),
    })
    assert resp.status_code == 500
    assert "outside" in resp.json()["detail"].lower()


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
    assert "not found" in resp.json()["detail"].lower()


# ── Run endpoint ─────────────────────────────────────────────────────────────


def test_run_agent():
    """POST /run executes agent and returns result"""
    mock_result = MagicMock()
    mock_result.output = "I created the file for you."
    mock_usage = MagicMock()
    mock_usage.input_tokens = 100
    mock_usage.output_tokens = 50
    mock_usage.total_tokens = 150
    mock_result.usage.return_value = mock_usage

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
    mock_result = MagicMock()
    mock_result.output = "done"
    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_usage.total_tokens = 15
    mock_result.usage.return_value = mock_usage

    with patch("cody.server.AgentRunner") as MockRunner:
        instance = MockRunner.return_value
        instance.run = AsyncMock(return_value=mock_result)

        with patch("cody.server.Config.load") as mock_load:
            config = MagicMock()
            config.model = "anthropic:claude-sonnet-4-0"
            config.skills = MagicMock()
            mock_load.return_value = config

            client = TestClient(app)
            resp = client.post("/run", json={
                "prompt": "test",
                "model": "openai:gpt-4o",
            })

    assert resp.status_code == 200
    # Verify model was overridden
    assert config.model == "openai:gpt-4o"


def test_run_agent_with_workdir(tmp_path):
    """POST /run respects workdir"""
    mock_result = MagicMock()
    mock_result.output = "done"
    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_usage.total_tokens = 15
    mock_result.usage.return_value = mock_usage

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
    assert "LLM API error" in resp.json()["detail"]


# ── Stream endpoint ──────────────────────────────────────────────────────────


def test_run_stream():
    """POST /run/stream returns SSE stream"""
    async def fake_stream(prompt, message_history=None):
        for chunk in ["Hello", " ", "World"]:
            yield chunk

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
    assert "data: Hello" in body
    assert "data: World" in body
    assert "data: [DONE]" in body


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
    assert "[ERROR]" in resp.text


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
