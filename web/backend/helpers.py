"""Shared helper functions for the web backend.

Migrated from cody/server.py — stream event serialization, error raising,
config loading from request.
"""

from pathlib import Path
from typing import Any, Optional

from typing import List

from cody.core import AgentRunner, Config
from cody.core.errors import CodyAPIError, ErrorCode
from cody.core.prompt import ImageData, MultimodalPrompt, Prompt

from .state import get_config, get_runner


def raise_structured(
    code: ErrorCode,
    message: str,
    status_code: int = 400,
    details: Optional[dict[str, Any]] = None,
):
    """Raise a CodyAPIError with the given fields."""
    raise CodyAPIError(
        code=code,
        message=message,
        status_code=status_code,
        details=details,
    )


def serialize_stream_event(event, session_id: Optional[str] = None) -> dict:
    """Convert a StreamEvent to a JSON-serializable dict for SSE/WebSocket."""
    from cody.core.runner import (
        CancelledEvent, CompactEvent, ThinkingEvent, TextDeltaEvent,
        ToolCallEvent, ToolResultEvent, DoneEvent, CircuitBreakerEvent,
        InteractionRequestEvent, UserInputReceivedEvent, RetryEvent,
    )

    base: dict[str, Any] = {"type": event.event_type}
    if session_id:
        base["session_id"] = session_id

    if isinstance(event, CompactEvent):
        base["original_messages"] = event.original_messages
        base["compacted_messages"] = event.compacted_messages
        base["estimated_tokens_saved"] = event.estimated_tokens_saved
        base["used_llm"] = event.used_llm
    elif isinstance(event, ThinkingEvent):
        base["content"] = event.content
    elif isinstance(event, TextDeltaEvent):
        base["content"] = event.content
    elif isinstance(event, ToolCallEvent):
        base["tool_name"] = event.tool_name
        base["args"] = event.args
        base["tool_call_id"] = event.tool_call_id
    elif isinstance(event, ToolResultEvent):
        base["tool_name"] = event.tool_name
        base["tool_call_id"] = event.tool_call_id
        base["result"] = event.result[:500]
    elif isinstance(event, DoneEvent):
        base["output"] = event.result.output
        base["thinking"] = event.result.thinking
        if event.result.tool_traces:
            base["tool_traces"] = [
                {
                    "tool_name": t.tool_name,
                    "args": t.args,
                    "result": t.result[:500],
                }
                for t in event.result.tool_traces
            ]
        usage = event.result.usage()
        if usage:
            base["usage"] = {
                "total_tokens": usage.total_tokens,
            }
        if event.result.metadata:
            base["metadata"] = {
                "summary": event.result.metadata.summary,
                "confidence": event.result.metadata.confidence,
            }
    elif isinstance(event, CancelledEvent):
        pass  # base already has {"type": "cancelled"}
    elif isinstance(event, CircuitBreakerEvent):
        base["reason"] = event.reason
        base["tokens_used"] = event.tokens_used
        base["cost_usd"] = event.cost_usd
    elif isinstance(event, InteractionRequestEvent):
        base["request_id"] = event.request.id
        base["kind"] = event.request.kind
        base["prompt"] = event.request.prompt
        base["options"] = event.request.options
    elif isinstance(event, RetryEvent):
        base["attempt"] = event.attempt
        base["max_attempts"] = event.max_attempts
        base["error"] = event.error
    elif isinstance(event, UserInputReceivedEvent):
        base["content"] = event.content

    return base


def serialize_runtime_event(
    event, session_id: Optional[str] = None, model_result=None
) -> Optional[dict]:
    """Serialize canonical Runtime events into the established Web stream API."""

    from cody.core.runtime.events import RunEventType

    payload = event.payload
    mapping = {
        RunEventType.SESSION_STARTED: "session_start",
        RunEventType.MODEL_THINKING_DELTA: "thinking",
        RunEventType.MODEL_TEXT_DELTA: "text_delta",
        RunEventType.TOOL_CALL_STARTED: "tool_call",
        RunEventType.TOOL_CALL_COMPLETED: "tool_result",
        RunEventType.CONTEXT_COMPACTED: "compact",
        RunEventType.CONTEXT_PRUNED: "prune",
        RunEventType.MODEL_RETRYING: "retry",
        RunEventType.CIRCUIT_BREAKER_TRIGGERED: "circuit_breaker",
        RunEventType.HUMAN_INPUT_REQUESTED: "interaction_request",
        RunEventType.USER_INPUT_RECEIVED: "user_input_received",
        RunEventType.RUN_CANCELLED: "cancelled",
        RunEventType.RUN_COMPLETED: "done",
    }
    web_type = mapping.get(event.event_type)
    if web_type is None:
        return None
    result: dict[str, Any] = {"type": web_type, "run_id": event.run_id}
    effective_sid = payload.get("session_id") or session_id
    if effective_sid:
        result["session_id"] = effective_sid
    if web_type in {"thinking", "text_delta", "user_input_received"}:
        result["content"] = str(payload.get("content") or "")
    elif web_type == "tool_call":
        result.update({
            "tool_name": payload.get("tool_name"),
            "args": payload.get("args") or {},
            "tool_call_id": payload.get("tool_call_id"),
        })
    elif web_type == "tool_result":
        result.update({
            "tool_name": payload.get("tool_name"),
            "tool_call_id": payload.get("tool_call_id"),
            "result": str(payload.get("result") or "")[:500],
        })
    elif web_type in {"compact", "prune", "retry", "circuit_breaker"}:
        result.update({
            key: value for key, value in payload.items()
            if key not in {"legacy_event_type", "event_scope", "checkpoint_id"}
        })
    elif web_type == "interaction_request":
        request = payload.get("request") or {}
        result.update({
            "request_id": request.get("id"),
            "kind": request.get("kind"),
            "prompt": request.get("prompt"),
            "options": request.get("options"),
        })
    elif web_type == "done":
        result["output"] = str(payload.get("output") or "")
        if model_result is not None:
            result["thinking"] = model_result.thinking
            if model_result.tool_traces:
                result["tool_traces"] = [
                    {
                        "tool_name": trace.tool_name,
                        "args": trace.args,
                        "result": trace.result[:500],
                    }
                    for trace in model_result.tool_traces
                ]
            usage = model_result.usage()
            if usage:
                result["usage"] = {"total_tokens": usage.total_tokens}
            if model_result.metadata:
                result["metadata"] = {
                    "summary": model_result.metadata.summary,
                    "confidence": model_result.metadata.confidence,
                }
        elif payload.get("usage"):
            result["usage"] = {
                "total_tokens": payload["usage"].get("total_tokens", 0)
            }
    return result


def build_prompt(text: str, images_raw: Optional[List[dict]] = None) -> Prompt:
    """Build a Prompt from text and optional raw image dicts.

    Used by all routes (chat, run, websocket) to convert frontend payloads
    into the core Prompt type.
    """
    if not images_raw:
        return text
    images = [
        ImageData(
            data=img["data"],
            media_type=img["media_type"],
            filename=img.get("filename"),
        )
        for img in images_raw
    ]
    return MultimodalPrompt(text=text, images=images)


def resolve_chat_runner(
    workdir: Path,
    data: dict,
    code_paths: list[str] | None = None,
) -> tuple[Config, AgentRunner]:
    """Build Config + AgentRunner from WebSocket message data.

    Handles config loading, API key check, per-message overrides, and
    extra_roots from project code_paths.

    Raises ValueError if no API key is configured.
    """
    config = get_config(workdir)

    if not data.get("model_api_key") and not config.is_ready():
        raise ValueError("No API key configured")

    extra_roots = [Path(p) for p in (code_paths or []) if p]

    # Collect all override keys to decide whether to create a fresh runner
    model_overrides = {
        k: data.get(k)
        for k in ("model", "model_base_url", "model_api_key",
                  "enable_thinking", "thinking_budget")
        if data.get(k)
    }
    cb_overrides = {
        k: data.get(k)
        for k in ("max_tokens", "max_cost_usd", "max_steps")
        if data.get(k) is not None
    }
    has_overrides = bool(model_overrides) or bool(cb_overrides)

    if model_overrides:
        config.apply_overrides(
            model=data.get("model"),
            model_base_url=data.get("model_base_url"),
            model_api_key=data.get("model_api_key"),
            enable_thinking=data.get("enable_thinking"),
            thinking_budget=data.get("thinking_budget"),
        )

    # Apply circuit breaker overrides (before runner creation so they take effect)
    if cb_overrides:
        if "max_tokens" in cb_overrides:
            config.circuit_breaker.max_tokens = cb_overrides["max_tokens"]
        if "max_cost_usd" in cb_overrides:
            config.circuit_breaker.max_cost_usd = cb_overrides["max_cost_usd"]
        if "max_steps" in cb_overrides:
            config.circuit_breaker.max_steps = cb_overrides["max_steps"]

    # Create a new runner if any overrides or extra_roots are present;
    # otherwise use the cached runner.  Never mutate a cached runner's config.
    if has_overrides or extra_roots:
        runner = AgentRunner(config=config, workdir=workdir, extra_roots=extra_roots)
    else:
        runner = get_runner(workdir)

    # Enable interaction so the AI can ask questions via WebSocket.
    # Must set on runner.config (not the local config copy) so the
    # stream interaction handler picks it up.
    runner.config.interaction.enabled = True

    return config, runner


def config_from_run_request(request) -> Config:
    """Load config (cached) and apply request-level overrides on a copy."""
    workdir = Path(request.workdir) if request.workdir else Path.cwd()
    cfg = get_config(workdir).apply_overrides(
        model=request.model,
        model_base_url=request.model_base_url,
        model_api_key=request.model_api_key,
        enable_thinking=request.enable_thinking,
        thinking_budget=request.thinking_budget,
        skills=request.skills,
        extra_roots=request.allowed_roots,
    )
    # Apply circuit breaker overrides from request
    if request.max_tokens is not None:
        cfg.circuit_breaker.max_tokens = request.max_tokens
    if request.max_cost_usd is not None:
        cfg.circuit_breaker.max_cost_usd = request.max_cost_usd
    if request.max_steps is not None:
        cfg.circuit_breaker.max_steps = request.max_steps
    return cfg
