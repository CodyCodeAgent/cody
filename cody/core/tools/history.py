"""File history tools — undo, redo, list changes."""

from pydantic_ai import RunContext

from ..deps import CodyDeps
from ._base import _check_permission


async def undo_file(ctx: RunContext['CodyDeps']) -> str:
    """Undo the last file modification, restoring the file to its previous content"""
    await _check_permission(ctx, "undo_file")
    history = ctx.deps.file_history
    if history is None:
        return "[ERROR] File history not available"

    change = history.undo()
    if change is None:
        return "Nothing to undo"

    if ctx.deps.audit_logger:
        ctx.deps.audit_logger.log(
            event="file_edit",
            tool_name="undo_file",
            args_summary=f"path={change.file_path}",
            result_summary=f"Undid {change.operation} on {change.file_path}",
            workdir=str(ctx.deps.workdir),
        )

    return f"Undid {change.operation} on {change.file_path} (from {change.timestamp})"


async def redo_file(ctx: RunContext['CodyDeps']) -> str:
    """Redo a previously undone file modification"""
    await _check_permission(ctx, "redo_file")
    history = ctx.deps.file_history
    if history is None:
        return "[ERROR] File history not available"

    change = history.redo()
    if change is None:
        return "Nothing to redo"

    if ctx.deps.audit_logger:
        ctx.deps.audit_logger.log(
            event="file_edit",
            tool_name="redo_file",
            args_summary=f"path={change.file_path}",
            result_summary=f"Redid {change.operation} on {change.file_path}",
            workdir=str(ctx.deps.workdir),
        )

    return f"Redid {change.operation} on {change.file_path}"


async def list_file_changes(ctx: RunContext['CodyDeps']) -> str:
    """List recent file modifications that can be undone"""
    history = ctx.deps.file_history
    if history is None:
        return "[ERROR] File history not available"

    changes = history.list_changes()
    if not changes:
        return "No file changes recorded"

    lines = [f"File changes ({len(changes)} undoable, {history.redo_count} redoable):"]
    for c in changes:
        lines.append(f"  [{c.operation}] {c.file_path} ({c.timestamp})")

    return "\n".join(lines)
