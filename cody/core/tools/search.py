"""Search tools — grep, glob, patch, search_files."""

import fnmatch
import re

from pydantic_ai import RunContext

from ..deps import CodyDeps
from ..errors import ToolInvalidParams
from ._base import _check_permission, _resolve_and_check
from ._file_filter import (
    _DEFAULT_IGNORE_FILES,
    _is_binary,
    _is_gitignored,
    _is_ignored_dir,
    _iter_files,
    _parse_gitignore,
)


async def grep(
    ctx: RunContext['CodyDeps'],
    pattern: str,
    path: str = ".",
    include: str = "",
) -> str:
    """Search file contents using a regular expression

    Args:
        pattern: Regular expression pattern to search for
        path: Directory or file to search in (relative or absolute)
        include: Optional glob to filter filenames (e.g. "*.py")
    """
    full_path = _resolve_and_check(
        ctx.deps.workdir, path, allow_read_outside=True, allowed_roots=ctx.deps.allowed_roots
    )

    if not full_path.exists():
        raise ToolInvalidParams(f"Path not found: {path}")

    try:
        regex = re.compile(pattern)
    except re.error as e:
        raise ToolInvalidParams(f"Invalid regex pattern: {e}")

    matches: list[str] = []
    max_matches = 200
    workdir_resolved = ctx.deps.workdir.resolve()

    if full_path.is_file():
        files = [full_path]
    else:
        gitignore_patterns = _parse_gitignore(workdir_resolved)
        files = _iter_files(full_path, workdir_resolved, gitignore_patterns)

    for file_path in files:
        if not file_path.is_file():
            continue
        if include and not fnmatch.fnmatch(file_path.name, include):
            continue
        if _is_binary(file_path):
            continue

        try:
            content = file_path.read_text(errors="ignore")
        except (PermissionError, OSError):
            continue

        rel = file_path.relative_to(workdir_resolved)
        for line_no, line in enumerate(content.splitlines(), 1):
            if regex.search(line):
                matches.append(f"{rel}:{line_no}: {line.rstrip()}")
                if len(matches) >= max_matches:
                    matches.append(f"... (truncated at {max_matches} matches)")
                    return "\n".join(matches)

    if not matches:
        return f"No matches found for pattern: {pattern}"

    return "\n".join(matches)


async def glob(
    ctx: RunContext['CodyDeps'],
    pattern: str,
    path: str = ".",
) -> str:
    """Find files by glob pattern

    Args:
        pattern: Glob pattern (e.g. "**/*.py", "*.txt", "src/**/*.ts")
        path: Base directory to search from (relative or absolute)
    """
    full_path = _resolve_and_check(
        ctx.deps.workdir, path, allow_read_outside=True, allowed_roots=ctx.deps.allowed_roots
    )

    if not full_path.exists():
        raise ToolInvalidParams(f"Path not found: {path}")

    if not full_path.is_dir():
        raise ToolInvalidParams(f"Not a directory: {path}")

    workdir_resolved = ctx.deps.workdir.resolve()
    gitignore_patterns = _parse_gitignore(workdir_resolved)
    results: list[str] = []
    max_results = 500
    all_roots = [workdir_resolved] + [r.resolve() for r in (ctx.deps.allowed_roots or [])]

    for match in sorted(full_path.glob(pattern)):
        # Security: skip anything outside all permitted roots
        resolved_match = match.resolve()
        if not any(resolved_match.is_relative_to(root) for root in all_roots):
            continue

        try:
            rel = match.relative_to(workdir_resolved)
        except ValueError:
            # File is in an allowed_root outside workdir — show absolute path
            rel = match
        rel_posix = str(rel).replace('\\', '/')
        is_dir = match.is_dir()

        # Check if any parent directory is ignored
        skip = False
        for part in rel.parts[:-1]:
            if _is_ignored_dir(part):
                skip = True
                break
        if skip:
            continue

        # Check the item itself
        if is_dir and _is_ignored_dir(match.name):
            continue
        if not is_dir and match.name in _DEFAULT_IGNORE_FILES:
            continue

        # Check gitignore
        if gitignore_patterns and _is_gitignored(rel_posix, gitignore_patterns, is_dir=is_dir):
            continue

        prefix = "[dir]" if is_dir else "[file]"
        results.append(f"{prefix} {rel}")
        if len(results) >= max_results:
            results.append(f"... (truncated at {max_results} results)")
            break

    if not results:
        return f"No files matched pattern: {pattern}"

    return "\n".join(results)


async def patch(
    ctx: RunContext['CodyDeps'],
    path: str,
    diff: str,
) -> str:
    """Apply a unified diff patch to a file

    Args:
        path: Path to the file to patch
        diff: Unified diff content (lines starting with +/- and context lines)
    """
    _check_permission(ctx, "patch")
    full_path = _resolve_and_check(ctx.deps.workdir, path, allowed_roots=ctx.deps.allowed_roots)

    if not full_path.exists():
        raise ToolInvalidParams(f"File not found: {path}")

    original_lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    result_lines: list[str] = []
    orig_idx = 0

    diff_lines = diff.splitlines(keepends=True)
    i = 0

    while i < len(diff_lines):
        line = diff_lines[i]

        # Skip diff headers
        if line.startswith("---") or line.startswith("+++"):
            i += 1
            continue

        # Parse hunk header
        if line.startswith("@@"):
            hunk_match = re.match(r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@", line)
            if not hunk_match:
                raise ToolInvalidParams(f"Invalid hunk header: {line.rstrip()}")
            hunk_start = int(hunk_match.group(1)) - 1  # 0-indexed
            if hunk_start < 0 or hunk_start > len(original_lines):
                raise ToolInvalidParams(
                    f"Invalid hunk start line {hunk_start + 1}: "
                    f"file has {len(original_lines)} lines"
                )

            # Copy lines before this hunk
            while orig_idx < hunk_start:
                if orig_idx < len(original_lines):
                    result_lines.append(original_lines[orig_idx])
                orig_idx += 1

            i += 1
            # Process hunk lines
            while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
                dl = diff_lines[i]
                if dl.startswith("-"):
                    # Remove line — skip it from original
                    orig_idx += 1
                elif dl.startswith("+"):
                    # Add line
                    content = dl[1:]
                    if not content.endswith("\n"):
                        content += "\n"
                    result_lines.append(content)
                elif dl.startswith(" ") or dl.strip() == "":
                    # Context line
                    if orig_idx < len(original_lines):
                        result_lines.append(original_lines[orig_idx])
                    orig_idx += 1
                else:
                    break
                i += 1
        else:
            i += 1

    # Copy remaining lines
    while orig_idx < len(original_lines):
        result_lines.append(original_lines[orig_idx])
        orig_idx += 1

    patched_content = "".join(result_lines)
    full_path.write_text(patched_content, encoding="utf-8")

    # Track in file history
    if ctx.deps.file_history:
        original_content = "".join(original_lines)
        ctx.deps.file_history.record(path, original_content, patched_content, operation="patch")

    # Audit log
    if ctx.deps.audit_logger:
        ctx.deps.audit_logger.log(
            event="file_edit",
            tool_name="patch",
            args_summary=f"path={path}",
            result_summary=f"Patched {path}",
            workdir=str(ctx.deps.workdir),
        )

    return f"Patched {path} successfully"


async def search_files(
    ctx: RunContext['CodyDeps'],
    query: str,
    path: str = ".",
) -> str:
    """Search for files by name (fuzzy match)

    Args:
        query: Search query to match against file names
        path: Directory to search in (relative or absolute)
    """
    full_path = _resolve_and_check(
        ctx.deps.workdir, path, allow_read_outside=True, allowed_roots=ctx.deps.allowed_roots
    )

    if not full_path.exists():
        raise ToolInvalidParams(f"Path not found: {path}")

    if not full_path.is_dir():
        raise ToolInvalidParams(f"Not a directory: {path}")

    workdir_resolved = ctx.deps.workdir.resolve()
    gitignore_patterns = _parse_gitignore(workdir_resolved)
    query_lower = query.lower()

    results: list[tuple[int, str]] = []
    max_results = 100

    for file_path in _iter_files(full_path, workdir_resolved, gitignore_patterns):
        name_lower = file_path.name.lower()
        rel = str(file_path.relative_to(workdir_resolved))

        # Scoring: exact match > starts with > contains > path contains
        if name_lower == query_lower:
            score = 0
        elif name_lower.startswith(query_lower):
            score = 1
        elif query_lower in name_lower:
            score = 2
        elif query_lower in rel.lower():
            score = 3
        else:
            continue

        results.append((score, rel))

    results.sort()
    output = [r[1] for r in results[:max_results]]

    if not output:
        return f"No files found matching: {query}"

    if len(results) > max_results:
        output.append(f"... ({len(results) - max_results} more)")

    return "\n".join(output)
