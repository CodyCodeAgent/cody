"""Tests for Cody SDK (cody.sdk) — builder, config, events, metrics, errors."""

import pytest
from unittest.mock import AsyncMock, patch

from cody.sdk.config import SDKConfig, ModelConfig, PermissionConfig, SecurityConfig, CircuitBreakerConfig, MCPConfig, LSPConfig, config
from cody.sdk.errors import (
    CodyError,
    CodyModelError,
    CodyToolError,
    CodyPermissionError,
    CodySessionError,
    CodyRateLimitError,
    CodyConfigError,
    CodyTimeoutError,
    CodyConnectionError,
    CodyNotFoundError,
)
from cody.sdk.events import (
    EventManager,
    EventType,
    Event,
    RunEvent,
    ToolEvent,
    StreamEvent,
    SessionEvent,
    ModelEvent,
    ContextCompactEvent,
    create_print_handler,
    create_collector_handler,
)
from cody.sdk.metrics import MetricsCollector, TokenUsage, ToolMetrics
from cody.sdk.client import CodyBuilder, Cody, AsyncCodyClient, CodyClient


# ── Config Tests ────────────────────────────────────────────────────────────


def test_model_config_defaults():
    cfg = ModelConfig()
    assert cfg.model == ""
    assert cfg.base_url is None
    assert cfg.api_key is None
    assert cfg.enable_thinking is False


def test_model_config_to_dict():
    cfg = ModelConfig(model="test:model", base_url="http://localhost", api_key="sk-test")
    d = cfg.to_dict()
    assert d["model"] == "test:model"
    assert d["model_base_url"] == "http://localhost"
    assert d["model_api_key"] == "sk-test"


def test_model_config_to_dict_minimal():
    cfg = ModelConfig()
    d = cfg.to_dict()
    assert d == {"model": ""}


def test_permission_config():
    cfg = PermissionConfig(default_level="allow", overrides={"exec_command": "deny"})
    d = cfg.to_dict()
    assert d["default_level"] == "allow"
    assert d["overrides"]["exec_command"] == "deny"


def test_security_config():
    cfg = SecurityConfig(allowed_roots=["/tmp"], enable_audit=False)
    d = cfg.to_dict()
    assert d["allowed_roots"] == ["/tmp"]
    assert d["enable_audit"] is False


def test_mcp_config_disabled():
    cfg = MCPConfig(enabled=False)
    d = cfg.to_dict()
    assert d["servers"] == []


def test_lsp_config_defaults():
    cfg = LSPConfig()
    assert "python" in cfg.languages
    assert cfg.enabled is True


def test_sdk_config_defaults():
    cfg = SDKConfig()
    assert cfg.workdir is None
    assert cfg.enable_metrics is False
    assert cfg.enable_events is False
    assert cfg.model.model == ""


def test_sdk_config_from_dict():
    data = {
        "workdir": "/tmp/project",
        "model": "test:model",
        "enable_metrics": True,
        "permissions": {"default_level": "allow", "overrides": {}},
    }
    cfg = SDKConfig.from_dict(data)
    assert cfg.workdir == "/tmp/project"
    assert cfg.model.model == "test:model"
    assert cfg.enable_metrics is True
    assert cfg.permissions.default_level == "allow"


def test_sdk_config_from_dict_model_dict():
    data = {"model": {"model": "test:model", "api_key": "sk-xxx"}}
    cfg = SDKConfig.from_dict(data)
    assert cfg.model.model == "test:model"
    assert cfg.model.api_key == "sk-xxx"


def test_config_convenience_function():
    cfg = config(
        model="test:model",
        workdir="/tmp",
        api_key="sk-test",
        enable_thinking=True,
        thinking_budget=5000,
        permissions={"exec_command": "allow"},
        allowed_roots=["/home"],
    )
    assert cfg.model.model == "test:model"
    assert cfg.workdir == "/tmp"
    assert cfg.model.api_key == "sk-test"
    assert cfg.model.enable_thinking is True
    assert cfg.model.thinking_budget == 5000
    assert cfg.permissions.overrides == {"exec_command": "allow"}
    assert cfg.security.allowed_roots == ["/home"]


def test_config_kwargs():
    cfg = config(enable_metrics=True, enable_events=True)
    assert cfg.enable_metrics is True
    assert cfg.enable_events is True


# ── Error Tests ─────────────────────────────────────────────────────────────


def test_cody_error_base():
    err = CodyError("test error", status_code=500, code="TEST")
    assert str(err) == "[TEST] test error"
    assert err.status_code == 500
    assert err.details == {}


def test_cody_error_without_code():
    err = CodyError("plain error")
    assert str(err) == "plain error"
    assert err.status_code == 0


def test_error_hierarchy():
    assert issubclass(CodyModelError, CodyError)
    assert issubclass(CodyToolError, CodyError)
    assert issubclass(CodyPermissionError, CodyError)
    assert issubclass(CodySessionError, CodyError)
    assert issubclass(CodyRateLimitError, CodyError)
    assert issubclass(CodyConfigError, CodyError)
    assert issubclass(CodyTimeoutError, CodyError)
    assert issubclass(CodyConnectionError, CodyError)
    assert issubclass(CodyNotFoundError, CodyError)


def test_cody_not_found_error():
    err = CodyNotFoundError("missing", resource_type="session", resource_id="abc")
    assert err.status_code == 404
    assert err.code == "NOT_FOUND"
    assert err.details["resource_type"] == "session"
    assert err.details["resource_id"] == "abc"


def test_cody_model_error():
    orig = ValueError("api failed")
    err = CodyModelError("model error", model="gpt-4", provider="openai", original_error=orig)
    assert err.status_code == 500
    assert err.code == "MODEL_ERROR"
    assert err.original_error is orig
    assert err.details["model"] == "gpt-4"


def test_cody_tool_error():
    err = CodyToolError("tool failed", tool_name="read_file")
    assert err.code == "TOOL_ERROR"
    assert err.details["tool_name"] == "read_file"


def test_cody_permission_error():
    err = CodyPermissionError("denied", tool_name="exec_command", required_level="allow")
    assert err.status_code == 403
    assert err.details["tool_name"] == "exec_command"


def test_cody_rate_limit_error():
    err = CodyRateLimitError("too many", retry_after=30, limit=100, remaining=0)
    assert err.status_code == 429
    assert err.retry_after == 30


def test_cody_timeout_error():
    err = CodyTimeoutError("timed out", operation="run", timeout=30.0)
    assert err.status_code == 408
    assert err.details["operation"] == "run"


def test_cody_connection_error():
    err = CodyConnectionError("failed", service="mcp")
    assert err.status_code == 503
    assert err.details["service"] == "mcp"


# ── Event Tests ─────────────────────────────────────────────────────────────


def test_event_type_values():
    assert EventType.RUN_START.value == "run_start"
    assert EventType.TOOL_CALL.value == "tool_call"
    assert EventType.STREAM_CHUNK.value == "stream_chunk"


def test_event_creation():
    event = Event(event_type=EventType.RUN_START)
    assert event.event_type == EventType.RUN_START
    assert event.timestamp > 0
    assert event.data == {}


def test_run_event():
    event = RunEvent(
        event_type=EventType.RUN_START,
        prompt="hello",
        session_id="s1",
    )
    assert event.prompt == "hello"
    assert event.session_id == "s1"
    assert event.result is None


def test_tool_event():
    event = ToolEvent(
        event_type=EventType.TOOL_CALL,
        tool_name="read_file",
        args={"path": "test.py"},
        duration=0.5,
    )
    assert event.tool_name == "read_file"
    assert event.args == {"path": "test.py"}
    assert event.duration == 0.5


def test_event_manager_sync_dispatch():
    em = EventManager()
    received = []

    @em.on(EventType.TOOL_CALL)
    def handler(event):
        received.append(event)

    event = ToolEvent(event_type=EventType.TOOL_CALL, tool_name="read_file")
    em.dispatch(event)

    assert len(received) == 1
    assert received[0].tool_name == "read_file"


def test_event_manager_register_method():
    em = EventManager()
    received = []

    def handler(event):
        received.append(event)

    em.register(EventType.RUN_START, handler)
    em.dispatch(RunEvent(event_type=EventType.RUN_START, prompt="test"))
    assert len(received) == 1


def test_event_manager_unregister():
    em = EventManager()
    received = []

    def handler(event):
        received.append(event)

    em.register(EventType.RUN_START, handler)
    em.unregister(EventType.RUN_START, handler)
    em.dispatch(RunEvent(event_type=EventType.RUN_START, prompt="test"))
    assert len(received) == 0


@pytest.mark.asyncio
async def test_event_manager_async_dispatch():
    em = EventManager()
    received = []

    @em.on_async(EventType.RUN_END)
    async def handler(event):
        received.append(event)

    event = RunEvent(event_type=EventType.RUN_END, prompt="test", result="done")
    await em.dispatch_async(event)

    assert len(received) == 1
    assert received[0].result == "done"


@pytest.mark.asyncio
async def test_event_manager_mixed_handlers():
    em = EventManager()
    sync_received = []
    async_received = []

    @em.on(EventType.TOOL_CALL)
    def sync_handler(event):
        sync_received.append(event)

    @em.on_async(EventType.TOOL_CALL)
    async def async_handler(event):
        async_received.append(event)

    event = ToolEvent(event_type=EventType.TOOL_CALL, tool_name="grep")
    await em.dispatch_async(event)

    assert len(sync_received) == 1
    assert len(async_received) == 1


def test_event_manager_disabled():
    em = EventManager(enabled=False)
    received = []

    @em.on(EventType.TOOL_CALL)
    def handler(event):
        received.append(event)

    em.dispatch(ToolEvent(event_type=EventType.TOOL_CALL, tool_name="test"))
    assert len(received) == 0


def test_event_manager_clear():
    em = EventManager()

    @em.on(EventType.TOOL_CALL)
    def handler(event):
        pass

    em.clear()
    assert len(em._handlers) == 0
    assert len(em._async_handlers) == 0


def test_event_manager_handler_error_caught():
    em = EventManager()

    @em.on(EventType.TOOL_CALL)
    def bad_handler(event):
        raise ValueError("oops")

    # Should not raise — error is logged
    em.dispatch(ToolEvent(event_type=EventType.TOOL_CALL, tool_name="test"))


def test_create_collector_handler():
    handler, collected = create_collector_handler()
    em = EventManager()
    em.register(EventType.TOOL_CALL, handler)

    em.dispatch(ToolEvent(event_type=EventType.TOOL_CALL, tool_name="a"))
    em.dispatch(ToolEvent(event_type=EventType.TOOL_CALL, tool_name="b"))

    assert len(collected) == 2
    assert collected[0].tool_name == "a"


def test_create_print_handler(capsys):
    handler = create_print_handler()
    handler(ToolEvent(event_type=EventType.TOOL_CALL, tool_name="read_file"))
    captured = capsys.readouterr()
    assert "tool_call" in captured.out
    assert "read_file" in captured.out


# ── Metrics Tests ───────────────────────────────────────────────────────────


def test_token_usage_add():
    a = TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15)
    b = TokenUsage(input_tokens=20, output_tokens=10, total_tokens=30)
    c = a.add(b)
    assert c.input_tokens == 30
    assert c.output_tokens == 15
    assert c.total_tokens == 45


def test_tool_metrics_defaults():
    m = ToolMetrics(tool_name="read_file")
    assert m.call_count == 0
    assert m.avg_duration == 0.0
    assert m.success_rate == 0.0


def test_tool_metrics_computed():
    m = ToolMetrics(
        tool_name="read_file",
        call_count=10,
        success_count=8,
        error_count=2,
        total_duration=5.0,
    )
    assert m.avg_duration == 0.5
    assert m.success_rate == 0.8


def test_metrics_collector_run_lifecycle():
    mc = MetricsCollector()
    mc.start_run("test prompt", session_id="s1", thinking=True)
    mc.record_tool_call("read_file", 0.5, success=True)
    mc.record_tool_call("grep", 0.3, success=True)
    mc.end_run("output", TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150))

    summary = mc.get_summary()
    assert summary["total_runs"] == 1
    assert summary["total_tokens"] == 150
    assert summary["total_tool_calls"] == 2
    assert "read_file" in summary["tool_metrics"]
    assert summary["tool_metrics"]["read_file"]["call_count"] == 1


def test_metrics_collector_tool_error():
    mc = MetricsCollector()
    mc.record_tool_call("exec_command", 1.0, success=False, error="permission denied")

    tools = mc.get_tool_metrics()
    assert tools["exec_command"].error_count == 1
    assert tools["exec_command"].success_rate == 0.0


def test_metrics_collector_session_tracking():
    mc = MetricsCollector()

    mc.start_run("prompt1", session_id="s1")
    mc.end_run("out1", TokenUsage(total_tokens=100))

    mc.start_run("prompt2", session_id="s1")
    mc.end_run("out2", TokenUsage(total_tokens=200))

    session = mc.get_session_metrics("s1")
    assert session is not None
    assert session.run_count == 2
    assert session.total_tokens.total_tokens == 300


def test_metrics_collector_disabled():
    mc = MetricsCollector()
    mc.disable()
    mc.start_run("test")
    mc.record_tool_call("test", 1.0)
    mc.end_run("out", TokenUsage(total_tokens=100))
    assert mc.get_summary()["total_runs"] == 0


def test_metrics_collector_reset():
    mc = MetricsCollector()
    mc.start_run("test")
    mc.end_run("out", TokenUsage(total_tokens=100))
    mc.reset()
    assert mc.get_summary()["total_runs"] == 0


def test_metrics_collector_export_json():
    mc = MetricsCollector()
    mc.start_run("test")
    mc.end_run("out", TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15))
    export = mc.export_json()
    assert "runs" in export
    assert len(export["runs"]) == 1
    assert export["runs"][0]["token_usage"]["total"] == 15


def test_metrics_get_run_history():
    mc = MetricsCollector()
    mc.start_run("p1")
    mc.end_run("o1", TokenUsage())
    mc.start_run("p2")
    mc.end_run("o2", TokenUsage())
    history = mc.get_run_history()
    assert len(history) == 2


# ── Builder Tests ───────────────────────────────────────────────────────────


def test_cody_factory():
    builder = Cody()
    assert isinstance(builder, CodyBuilder)


def test_builder_chaining():
    builder = (
        Cody()
        .workdir("/tmp")
        .model("test:model")
        .api_key("sk-test")
        .base_url("http://localhost")
        .thinking(True, budget=5000)
        .permission("exec_command", "allow")
        .allowed_root("/extra")
        .db_path("/tmp/test.db")
        .enable_metrics()
        .enable_events()
    )
    assert builder._workdir == "/tmp"
    assert builder._model == "test:model"
    assert builder._api_key == "sk-test"
    assert builder._base_url == "http://localhost"
    assert builder._enable_thinking is True
    assert builder._thinking_budget == 5000
    assert builder._permissions == {"exec_command": "allow"}
    assert "/extra" in builder._allowed_roots
    assert builder._db_path == "/tmp/test.db"
    assert builder._enable_metrics is True
    assert builder._enable_events is True


def test_builder_allowed_roots_list():
    builder = Cody().allowed_roots(["/a", "/b"])
    assert builder._allowed_roots == ["/a", "/b"]


def test_builder_mcp_server():
    builder = Cody().mcp_server({"name": "test", "command": "test-server"})
    assert len(builder._mcp_servers) == 1
    assert builder._mcp_servers[0]["name"] == "test"


def test_builder_lsp_languages():
    builder = Cody().lsp_languages(["rust", "java"])
    assert builder._lsp_languages == ["rust", "java"]


def test_builder_circuit_breaker_kwargs():
    builder = Cody().circuit_breaker(max_cost_usd=10.0, max_tokens=500_000)
    assert builder._circuit_breaker is not None
    assert builder._circuit_breaker.max_cost_usd == 10.0
    assert builder._circuit_breaker.max_tokens == 500_000
    assert builder._circuit_breaker.enabled is True


def test_builder_circuit_breaker_config_object():
    cb = CircuitBreakerConfig(max_cost_usd=20.0, enabled=False)
    builder = Cody().circuit_breaker(cb)
    assert builder._circuit_breaker.max_cost_usd == 20.0
    assert builder._circuit_breaker.enabled is False


def test_builder_circuit_breaker_model_prices():
    builder = Cody().circuit_breaker(
        max_cost_usd=8.0,
        model_prices={"claude-sonnet-4-0": 0.000009},
    )
    assert builder._circuit_breaker.model_prices == {"claude-sonnet-4-0": 0.000009}


def test_builder_circuit_breaker_build():
    client = (
        Cody()
        .workdir("/tmp")
        .model("test:model")
        .circuit_breaker(max_cost_usd=15.0, max_tokens=300_000)
        .build()
    )
    assert isinstance(client, AsyncCodyClient)
    assert client._config.circuit_breaker.max_cost_usd == 15.0
    assert client._config.circuit_breaker.max_tokens == 300_000


def test_sdk_config_circuit_breaker_defaults():
    cfg = SDKConfig()
    assert cfg.circuit_breaker.enabled is True
    assert cfg.circuit_breaker.max_cost_usd == 5.0
    assert cfg.circuit_breaker.max_tokens == 200_000


def test_sdk_config_from_dict_circuit_breaker():
    data = {
        "circuit_breaker": {
            "max_cost_usd": 12.0,
            "max_tokens": 400_000,
            "enabled": False,
        }
    }
    cfg = SDKConfig.from_dict(data)
    assert cfg.circuit_breaker.max_cost_usd == 12.0
    assert cfg.circuit_breaker.max_tokens == 400_000
    assert cfg.circuit_breaker.enabled is False


def test_builder_build():
    client = (
        Cody()
        .workdir("/tmp")
        .model("test:model")
        .enable_metrics()
        .enable_events()
        .build()
    )
    assert isinstance(client, AsyncCodyClient)
    assert client._config.model.model == "test:model"
    assert client._metrics is not None
    assert client._events is not None


# ── Client Tests ────────────────────────────────────────────────────────────


def test_async_client_init_defaults():
    client = AsyncCodyClient()
    assert client._config is not None
    assert client._runner is None  # lazy-initialized
    assert client._metrics is None
    assert client._events is None


def test_async_client_init_with_config():
    cfg = config(model="test:model", enable_metrics=True, enable_events=True)
    client = AsyncCodyClient(config=cfg)
    assert client._config.model.model == "test:model"
    assert client._metrics is not None
    assert client._events is not None


def test_async_client_init_with_params():
    client = AsyncCodyClient(
        workdir="/tmp",
        model="test:model",
        api_key="sk-test",
    )
    assert client._config.model.model == "test:model"
    assert client._config.workdir == "/tmp"


@pytest.mark.asyncio
async def test_async_client_context_manager():
    client = AsyncCodyClient()
    with patch.object(client, "close", new_callable=AsyncMock) as mock_close:
        async with client:
            pass
        mock_close.assert_called_once()


def test_async_client_events_not_enabled():
    client = AsyncCodyClient()
    with pytest.raises(CodyConfigError, match="Events not enabled"):
        client.on(EventType.TOOL_CALL, lambda e: None)


def test_async_client_on_with_events():
    cfg = config(enable_events=True)
    client = AsyncCodyClient(config=cfg)
    handler = lambda e: None  # noqa: E731
    client.on(EventType.TOOL_CALL, handler)
    assert handler in client._events._handlers[EventType.TOOL_CALL]


def test_async_client_metrics_none():
    client = AsyncCodyClient()
    assert client.get_metrics() is None


def test_async_client_metrics_enabled():
    cfg = config(enable_metrics=True)
    client = AsyncCodyClient(config=cfg)
    assert client.get_metrics_collector() is not None


def test_sync_client_init():
    client = CodyClient(workdir="/tmp")
    assert isinstance(client._async, AsyncCodyClient)


# ── Subclass event types ────────────────────────────────────────────────────


def test_stream_event():
    event = StreamEvent(
        event_type=EventType.STREAM_CHUNK,
        chunk_type="text_delta",
        content="hello",
    )
    assert event.chunk_type == "text_delta"
    assert event.content == "hello"


def test_session_event():
    event = SessionEvent(
        event_type=EventType.SESSION_CREATE,
        session_id="s1",
        title="Test",
    )
    assert event.session_id == "s1"
    assert event.title == "Test"


def test_model_event():
    event = ModelEvent(
        event_type=EventType.MODEL_RESPONSE,
        model="claude",
        input_tokens=100,
        output_tokens=50,
    )
    assert event.model == "claude"
    assert event.input_tokens == 100


def test_context_compact_event():
    event = ContextCompactEvent(
        event_type=EventType.CONTEXT_COMPACT,
        original_messages=20,
        compacted_messages=5,
        tokens_saved=3000,
    )
    assert event.original_messages == 20
    assert event.tokens_saved == 3000
