"""File operation tools — read, write, edit, list."""

from pydantic_ai import RunContext

from ..deps import CodyDeps
from ..errors import ToolInvalidParams
from ._base import _audit_tool_call, _check_permission, _resolve_and_check


async def read_file(ctx: RunContext['CodyDeps'], path: str) -> str:
    """Read file contents

    Args:
        path: Path to the file to read (relative or absolute)
    """
    full_path = _resolve_and_check(
        ctx.deps.workdir, path, allow_read_outside=not ctx.deps.strict_read_boundary, allowed_roots=ctx.deps.allowed_roots
    )

    if not full_path.exists():
        raise ToolInvalidParams(f"File not found: {path}")

    if full_path.is_dir():
        raise ToolInvalidParams(f"Path is a directory, not a file: {path}")

    return full_path.read_text(encoding="utf-8", errors="replace")


async def write_file(ctx: RunContext['CodyDeps'], path: str, content: str) -> str:
    """Write content to file

    Args:
        path: Path to the file
        content: Content to write
    """
    _check_permission(ctx, "write_file")
    full_path = _resolve_and_check(ctx.deps.workdir, path, allowed_roots=ctx.deps.allowed_roots)

    # Record old content for undo
    old_content = ""
    if full_path.exists():
        old_content = full_path.read_text(encoding="utf-8", errors="replace")

    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")

    # Track in file history
    if ctx.deps.file_history:
        ctx.deps.file_history.record(path, old_content, content, operation="write")

    _audit_tool_call(ctx, "file_write", "write_file", f"path={path}", f"Written {len(content)} bytes")

    return f"Written {len(content)} bytes to {path}"


async def edit_file(
    ctx: RunContext['CodyDeps'],
    path: str,
    old_text: str,
    new_text: str,
) -> str:
    """Edit file by replacing exact text

    Args:
        path: Path to the file
        old_text: Exact text to replace
        new_text: New text
    """
    _check_permission(ctx, "edit_file")
    full_path = _resolve_and_check(ctx.deps.workdir, path, allowed_roots=ctx.deps.allowed_roots)

    if not full_path.exists():
        raise ToolInvalidParams(f"File not found: {path}")

    content = full_path.read_text(encoding="utf-8", errors="replace")

    if old_text not in content:
        raise ToolInvalidParams(f"Text not found in file: {old_text[:50]}...")

    new_content = content.replace(old_text, new_text, 1)
    full_path.write_text(new_content, encoding="utf-8")

    # Track in file history
    if ctx.deps.file_history:
        ctx.deps.file_history.record(path, content, new_content, operation="edit")

    _audit_tool_call(ctx, "file_edit", "edit_file", f"path={path}", f"Replaced text in {path}")

    return f"Edited {path}: replaced text"


async def list_directory(ctx: RunContext['CodyDeps'], path: str = ".") -> str:
    """List directory contents

    Args:
        path: Directory path (relative or absolute)
    """
    full_path = _resolve_and_check(
        ctx.deps.workdir, path, allow_read_outside=not ctx.deps.strict_read_boundary, allowed_roots=ctx.deps.allowed_roots
    )

    if not full_path.exists():
        raise ToolInvalidParams(f"Directory not found: {path}")

    if not full_path.is_dir():
        raise ToolInvalidParams(f"Not a directory: {path}")

    items = []
    for item in sorted(full_path.iterdir()):
        prefix = "dir" if item.is_dir() else "file"
        items.append(f"[{prefix}] {item.name}")

    return "\n".join(items)
