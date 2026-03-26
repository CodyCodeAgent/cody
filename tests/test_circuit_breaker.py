"""Tests for CircuitBreaker, StructuredOutput, and related features."""

import pytest

from unittest.mock import patch

from cody.core.config import CircuitBreakerConfig, Config
from cody.core.errors import CircuitBreakerError
from cody.core.runner import (
    AgentRunner,
    CircuitBreakerEvent,
    InteractionRequestEvent,
    TaskMetadata,
    CodyResult,
    _extract_metadata,
)
from cody.core.interaction import InteractionRequest, InteractionResponse


# ── CircuitBreakerConfig ─────────────────────────────────────────────────────


class TestCircuitBreakerConfig:
    def test_defaults(self):
        cb = CircuitBreakerConfig()
        assert cb.enabled is True
        assert cb.max_tokens == 200_000
        assert cb.max_cost_usd == 5.0
        assert cb.max_steps == 0
        assert cb.loop_detect_turns == 6
        assert cb.loop_similarity_threshold == 0.9
        assert "default" in cb.model_prices

    def test_custom_values(self):
        cb = CircuitBreakerConfig(
            enabled=False,
            max_tokens=100_000,
            max_cost_usd=1.0,
            max_steps=50,
            loop_detect_turns=3,
            loop_similarity_threshold=0.8,
        )
        assert cb.enabled is False
        assert cb.max_tokens == 100_000
        assert cb.max_cost_usd == 1.0
        assert cb.max_steps == 50
        assert cb.loop_detect_turns == 3

    def test_config_has_circuit_breaker(self):
        config = Config()
        assert hasattr(config, "circuit_breaker")
        assert isinstance(config.circuit_breaker, CircuitBreakerConfig)
        assert config.circuit_breaker.enabled is True

    def test_serialization_roundtrip(self, tmp_path):
        config = Config()
        config.circuit_breaker.max_tokens = 50_000
        config.circuit_breaker.max_cost_usd = 2.5
        config.circuit_breaker.max_steps = 30
        path = tmp_path / "config.json"
        config.save(path)

        loaded = Config.load(path)
        assert loaded.circuit_breaker.max_tokens == 50_000
        assert loaded.circuit_breaker.max_cost_usd == 2.5
        assert loaded.circuit_breaker.max_steps == 30


# ── CircuitBreakerError ──────────────────────────────────────────────────────


class TestCircuitBreakerError:
    def test_token_limit(self):
        err = CircuitBreakerError("token_limit", 250_000, 0.75)
        assert err.reason == "token_limit"
        assert err.tokens_used == 250_000
        assert err.cost_usd == 0.75
        assert "token_limit" in str(err)

    def test_cost_limit(self):
        err = CircuitBreakerError("cost_limit", 100_000, 6.0)
        assert err.reason == "cost_limit"

    def test_loop_detected(self):
        err = CircuitBreakerError("loop_detected", 50_000)
        assert err.reason == "loop_detected"
        assert err.cost_usd == 0.0

    def test_step_limit(self):
        err = CircuitBreakerError("step_limit", 80_000, 0.24)
        assert err.reason == "step_limit"
        assert err.tokens_used == 80_000
        assert err.cost_usd == 0.24


# ── CircuitBreakerEvent ──────────────────────────────────────────────────────


class TestCircuitBreakerEvent:
    def test_event_fields(self):
        evt = CircuitBreakerEvent(
            reason="token_limit",
            tokens_used=200_001,
            cost_usd=0.6,
        )
        assert evt.event_type == "circuit_breaker"
        assert evt.reason == "token_limit"
        assert evt.tokens_used == 200_001
        assert evt.cost_usd == 0.6


# ── TaskMetadata & StructuredOutput ──────────────────────────────────────────


class TestTaskMetadata:
    def test_defaults(self):
        meta = TaskMetadata()
        assert meta.summary == ""
        assert meta.confidence is None
        assert meta.issues == []
        assert meta.next_steps == []

    def test_extract_metadata_basic(self):
        meta = _extract_metadata("Hello, I completed the task successfully.")
        assert meta.summary == "Hello, I completed the task successfully."
        assert meta.confidence is None

    def test_extract_metadata_with_confidence(self):
        output = "Done. <confidence>0.85</confidence>"
        meta = _extract_metadata(output)
        assert meta.confidence == 0.85

    def test_extract_metadata_confidence_bounds(self):
        # Value > 1.0 should be ignored
        meta = _extract_metadata("<confidence>1.5</confidence>")
        assert meta.confidence is None

        # Valid boundary
        meta = _extract_metadata("<confidence>0.0</confidence>")
        assert meta.confidence == 0.0

        meta = _extract_metadata("<confidence>1.0</confidence>")
        assert meta.confidence == 1.0

    def test_extract_metadata_invalid_confidence(self):
        meta = _extract_metadata("<confidence>abc</confidence>")
        assert meta.confidence is None

    def test_extract_metadata_empty_output(self):
        meta = _extract_metadata("")
        assert meta.summary == ""
        assert meta.confidence is None

    def test_cody_result_has_metadata(self):
        result = CodyResult(
            output="test output",
            metadata=TaskMetadata(summary="test", confidence=0.9),
        )
        assert result.metadata is not None
        assert result.metadata.confidence == 0.9

    def test_cody_result_metadata_default_none(self):
        result = CodyResult(output="test output")
        assert result.metadata is None


# ── InteractionRequest / InteractionResponse ─────────────────────────────────


class TestInteraction:
    def test_request_defaults(self):
        req = InteractionRequest()
        assert req.kind == "question"
        assert req.prompt == ""
        assert req.options == []
        assert req.context == {}
        assert req.confidence is None
        assert len(req.id) == 12

    def test_request_unique_ids(self):
        r1 = InteractionRequest()
        r2 = InteractionRequest()
        assert r1.id != r2.id

    def test_request_kinds(self):
        q = InteractionRequest(kind="question", prompt="What do you want?")
        c = InteractionRequest(kind="confirm", prompt="Write main.py?")
        f = InteractionRequest(kind="feedback", prompt="How was the result?")
        assert q.kind == "question"
        assert c.kind == "confirm"
        assert f.kind == "feedback"

    def test_response_defaults(self):
        resp = InteractionResponse()
        assert resp.action == "answer"
        assert resp.content == ""
        assert resp.request_id == ""

    def test_response_matching(self):
        req = InteractionRequest(kind="confirm", prompt="Delete file?")
        resp = InteractionResponse(request_id=req.id, action="approve")
        assert resp.request_id == req.id

    def test_response_actions(self):
        approve = InteractionResponse(action="approve")
        reject = InteractionResponse(action="reject")
        revise = InteractionResponse(action="revise", content="Use src/ instead")
        answer = InteractionResponse(action="answer", content="Yes")
        assert approve.action == "approve"
        assert reject.action == "reject"
        assert revise.action == "revise"
        assert answer.content == "Yes"

    def test_interaction_request_event(self):
        req = InteractionRequest(kind="confirm", prompt="Overwrite?")
        evt = InteractionRequestEvent(request=req)
        assert evt.event_type == "interaction_request"
        assert evt.request.kind == "confirm"


# ── Runner circuit breaker integration ───────────────────────────────────────


def _make_runner(cb_config: CircuitBreakerConfig) -> AgentRunner:
    """Create a minimal AgentRunner with circuit breaker state for testing."""
    from cody.core.runner import _CircuitBreakerState
    with patch.object(AgentRunner, "__init__", lambda self, **kw: None):
        runner = AgentRunner.__new__(AgentRunner)
        config = Config()
        config.circuit_breaker = cb_config
        runner.config = config
        runner._cb = _CircuitBreakerState()
        return runner


class TestCheckCircuitBreakerStepLimit:
    """Integration tests: _check_circuit_breaker raises on step_limit."""

    def test_step_limit_trips_when_reached(self):
        runner = _make_runner(CircuitBreakerConfig(max_steps=3))
        # Simulate 3 tool-call steps (reaches max_steps=3, trips on >=)
        for i in range(3):
            runner._update_circuit_breaker(f"result {i}", None)

        with pytest.raises(CircuitBreakerError) as exc_info:
            runner._check_circuit_breaker()
        assert exc_info.value.reason == "step_limit"

    def test_step_limit_ok_below_boundary(self):
        runner = _make_runner(CircuitBreakerConfig(max_steps=3))
        # 2 steps — below max_steps=3, should not trip
        for i in range(2):
            runner._update_circuit_breaker(f"result {i}", None)

        runner._check_circuit_breaker()  # no exception

    def test_step_limit_disabled_when_zero(self):
        runner = _make_runner(CircuitBreakerConfig(max_steps=0))
        # Many steps, but max_steps=0 means unlimited
        for i in range(100):
            runner._update_circuit_breaker(f"result {i}", None)

        runner._check_circuit_breaker()  # no exception

    def test_step_limit_disabled_when_cb_disabled(self):
        runner = _make_runner(CircuitBreakerConfig(enabled=False, max_steps=1))
        for i in range(5):
            runner._update_circuit_breaker(f"result {i}", None)

        runner._check_circuit_breaker()  # no exception — cb disabled

    def test_new_cb_clears_step_count(self):
        runner = _make_runner(CircuitBreakerConfig(max_steps=2))
        for i in range(3):
            runner._update_circuit_breaker(f"result {i}", None)

        # Should trip before reset
        with pytest.raises(CircuitBreakerError):
            runner._check_circuit_breaker()

        # After creating new CB state, should be fine
        runner._new_circuit_breaker()
        runner._check_circuit_breaker()  # no exception

    def test_empty_result_text_does_not_increment_step(self):
        runner = _make_runner(CircuitBreakerConfig(max_steps=1))
        # Empty string should not count as a step
        runner._update_circuit_breaker("", None)
        runner._update_circuit_breaker("", None)
        runner._update_circuit_breaker("", None)

        runner._check_circuit_breaker()  # no exception — 0 steps counted
