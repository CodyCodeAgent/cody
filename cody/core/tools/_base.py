"""Shared helpers used across tool modules."""

from __future__ import annotations

import functools
import logging
import time
from typing import TYPE_CHECKING

from pydantic_ai import ModelRetry, RunContext
from pathlib import Path

from ..errors import ToolError, ToolPathDenied
from ..interaction import InteractionRequest
from ..permissions import PermissionDeniedError, PermissionLevel

if TYPE_CHECKING:
    from ..deps import CodyDeps

_tool_logger = logging.getLogger("cody.core.tools")


async def _check_permission(ctx: RunContext['CodyDeps'], tool_name: str, args_summary: str = "") -> None:
    """Check permission before tool execution.

    - ALLOW: proceed immediately.
    - DENY: raise PermissionDeniedError.
    - CONFIRM + interaction enabled: pause and wait for human approval.
      If the human rejects, raise PermissionDeniedError.
    - CONFIRM + interaction disabled: auto-approve (backward compatible).
    """
    if not ctx.deps.permission_manager:
        return
    level = ctx.deps.permission_manager.check(tool_name)
    if level != PermissionLevel.CONFIRM:
        return
    # CONFIRM level — route through interaction handler if available
    handler = getattr(ctx.deps, "interaction_handler", None)
    if handler is None:
        return  # no handler → auto-approve (legacy)
    request = InteractionRequest(
        kind="confirm",
        prompt=f"Tool '{tool_name}' requires confirmation to execute.",
        context={"tool_name": tool_name, "args": args_summary},
    )
    response = await handler(request)
    if response.action == "reject":
        raise PermissionDeniedError(tool_name, f"User rejected execution of {tool_name}")


def _resolve_and_check(
    workdir: Path,
    path: str,
    *,
    allow_read_outside: bool = False,
    allowed_roots: list[Path] | None = None,
) -> Path:
    """Resolve path and verify it's inside an allowed directory. Returns resolved Path.

    *workdir* is always an implicit allowed root.  Additional roots can be
    supplied via *allowed_roots* (the access boundary).

    If *allow_read_outside* is True, paths that fall outside every allowed root
    are still permitted for read-only operations.  The caller is responsible
    for passing this flag only when appropriate.
    """
    if Path(path).is_absolute():
        full_path = Path(path).resolve()
    else:
        full_path = (workdir / path).resolve()

    roots: list[Path] = [workdir.resolve()]
    if allowed_roots:
        roots.extend(r.resolve() for r in allowed_roots)

    for root in roots:
        if full_path.is_relative_to(root):
            return full_path

    if allow_read_outside:
        return full_path
    roots_str = ', '.join(str(r) for r in roots)
    raise ToolPathDenied(
        f"Access denied: {path} is outside all permitted directories. "
        f"You can only access files within: {roots_str}. "
        f"Please use paths inside these directories."
    )


def _with_model_retry(func):
    """Wrap a tool function so ToolError is converted to ModelRetry.

    When a tool raises ToolError (e.g. ToolInvalidParams for "text not found"),
    pydantic-ai would normally propagate it as an unhandled exception, breaking
    the entire agent run. By converting it to ModelRetry, the error message is
    sent back to the model so it can correct its parameters and try again.

    Also logs elapsed time for every tool call at DEBUG level.
    """
    tool_name = func.__name__

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            elapsed = time.perf_counter() - start
            _tool_logger.debug("tool.%s completed in %.3fs", tool_name, elapsed)
            return result
        except ToolError as e:
            elapsed = time.perf_counter() - start
            _tool_logger.debug("tool.%s failed in %.3fs: %s", tool_name, elapsed, e)
            raise ModelRetry(str(e)) from e

    return wrapper


def _audit_tool_call(
    ctx: RunContext['CodyDeps'],
    event: str,
    tool_name: str,
    args_summary: str,
    result_summary: str,
    success: bool = True,
) -> None:
    """Log a tool call to the audit logger if available."""
    if ctx.deps.audit_logger:
        ctx.deps.audit_logger.log(
            event=event,
            tool_name=tool_name,
            args_summary=args_summary,
            result_summary=result_summary,
            workdir=str(ctx.deps.workdir),
            success=success,
        )
