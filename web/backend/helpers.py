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
        InteractionRequestEvent, UserInputReceivedEvent,
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
    elif isinstance(event, UserInputReceivedEvent):
        base["content"] = event.content

    return base


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

    overrides = {
        k: data.get(k)
        for k in ("model", "model_base_url", "model_api_key",
                  "enable_thinking", "thinking_budget")
        if data.get(k)
    }
    if overrides:
        config.apply_overrides(
            model=data.get("model"),
            model_base_url=data.get("model_base_url"),
            model_api_key=data.get("model_api_key"),
            enable_thinking=data.get("enable_thinking"),
            thinking_budget=data.get("thinking_budget"),
        )
        runner = AgentRunner(config=config, workdir=workdir, extra_roots=extra_roots)
    elif extra_roots:
        runner = AgentRunner(config=config, workdir=workdir, extra_roots=extra_roots)
    else:
        runner = get_runner(workdir)

    return config, runner


def config_from_run_request(request) -> Config:
    """Load config (cached) and apply request-level overrides on a copy."""
    workdir = Path(request.workdir) if request.workdir else Path.cwd()
    return get_config(workdir).apply_overrides(
        model=request.model,
        model_base_url=request.model_base_url,
        model_api_key=request.model_api_key,
        enable_thinking=request.enable_thinking,
        thinking_budget=request.thinking_budget,
        skills=request.skills,
        extra_roots=request.allowed_roots,
    )
