"""Core tools for Cody Agent.

Every tool has the same signature:
    async def tool_name(ctx: RunContext[CodyDeps], ...) -> str

Tools are grouped into categorized lists at the bottom of this file
(FILE_TOOLS, SEARCH_TOOLS, etc.). runner.py and sub_agent.py call
register_tools() / register_sub_agent_tools() instead of hard-coding
individual agent.tool() calls — adding a new tool is one list edit.

Error conventions:
  - ToolInvalidParams  → bad arguments          (server maps to 400)
  - ToolPathDenied     → path outside workdir    (server maps to 403)
  - ToolPermissionDenied → permission check fail (server maps to 403)
  - FileNotFoundError  → missing file/dir        (server maps to 500)

In agent context, all ToolError subclasses are automatically converted to
pydantic-ai ModelRetry (via _with_model_retry wrapper in register_tools),
so the model can self-correct and retry instead of breaking the run.
"""

import fnmatch
import functools
import logging
import os
import re
import subprocess
import time
from pathlib import Path

from pydantic_ai import ModelRetry, RunContext

from .deps import CodyDeps
from .errors import ToolError, ToolPermissionDenied, ToolPathDenied, ToolInvalidParams

_tool_logger = logging.getLogger(__name__)


def _check_permission(ctx: RunContext['CodyDeps'], tool_name: str) -> None:
    """Check permission before tool execution. Raises ToolPermissionDenied if denied."""
    if ctx.deps.permission_manager:
        ctx.deps.permission_manager.check(tool_name)


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
    raise ToolPathDenied(
        f"Access denied: {path} is outside all permitted directories "
        f"({', '.join(str(r) for r in roots)}). "
        f"Tip: add paths to security.allowed_roots in .cody/config.json, "
        f"or use --allow-root at the command line."
    )


# ── File filtering (binary detection, gitignore, default ignores) ────────────

# Directories to always skip (matches ripgrep defaults)
_DEFAULT_IGNORE_DIRS = frozenset({
    '.git', '.hg', '.svn', '.bzr', 'CVS',
    'node_modules', '__pycache__',
    '.venv', 'venv',
    'dist', 'build', '_build',
    '.eggs', '.tox',
    '.mypy_cache', '.pytest_cache', '.ruff_cache',
    '.cache', '.sass-cache',
    'target',
})

_DEFAULT_IGNORE_FILES = frozenset({
    '.DS_Store', 'Thumbs.db',
})

_BINARY_CHECK_SIZE = 8192


def _is_binary(file_path: Path) -> bool:
    """Check if a file is binary by looking for null bytes in the first 8KB."""
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(_BINARY_CHECK_SIZE)
        return b'\x00' in chunk
    except (OSError, PermissionError):
        return True


def _parse_gitignore(workdir: Path) -> list[str]:
    """Parse .gitignore from workdir root and return active patterns."""
    gitignore = workdir / '.gitignore'
    if not gitignore.is_file():
        return []
    try:
        lines = gitignore.read_text(errors='ignore').splitlines()
    except (OSError, PermissionError):
        return []
    patterns = []
    for line in lines:
        line = line.rstrip()
        if not line or line.startswith('#'):
            continue
        patterns.append(line)
    return patterns


def _gitignore_match(rel_posix: str, pattern: str, is_dir: bool) -> bool:
    """Test if a relative POSIX path matches a single gitignore pattern."""
    dir_only = pattern.endswith('/')
    if dir_only:
        pattern = pattern.rstrip('/')
        if not is_dir:
            # Check if a parent directory component matches
            parts = rel_posix.split('/')
            return any(fnmatch.fnmatch(p, pattern) for p in parts[:-1])

    anchored = pattern.startswith('/')
    if anchored:
        pattern = pattern[1:]

    # Contains slash (besides leading/trailing) → path pattern
    if '/' in pattern or anchored:
        return fnmatch.fnmatch(rel_posix, pattern)

    # Simple pattern: match against basename at any depth
    basename = rel_posix.rsplit('/', 1)[-1] if '/' in rel_posix else rel_posix
    if fnmatch.fnmatch(basename, pattern):
        return True
    # For dir-only pattern, also check directory components
    if dir_only:
        parts = rel_posix.split('/')
        return any(fnmatch.fnmatch(p, pattern) for p in parts[:-1])
    return False


def _is_gitignored(rel_posix: str, patterns: list[str], is_dir: bool = False) -> bool:
    """Check if path matches gitignore patterns (supports ! negation)."""
    matched = False
    for pat in patterns:
        negate = pat.startswith('!')
        if negate:
            pat = pat[1:]
        if _gitignore_match(rel_posix, pat, is_dir):
            matched = not negate
    return matched


def _is_ignored_dir(name: str) -> bool:
    """Check if a directory name should be skipped."""
    if name in _DEFAULT_IGNORE_DIRS:
        return True
    if name.startswith('.') and name not in ('.', '..'):
        return True
    return False


def _iter_files(
    root: Path,
    workdir_resolved: Path,
    gitignore_patterns: list[str],
) -> list[Path]:
    """Walk directory tree yielding non-ignored files.

    Prunes hidden/default-ignored directories and respects .gitignore.
    Does NOT filter binary files (caller decides).
    """
    result: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)

        # Prune ignored directories in-place for efficiency
        filtered_dirs = []
        for d in sorted(dirnames):
            if _is_ignored_dir(d):
                continue
            try:
                rel = str((current / d).relative_to(workdir_resolved))
                rel_posix = rel.replace('\\', '/')
            except ValueError:
                continue
            if gitignore_patterns and _is_gitignored(rel_posix, gitignore_patterns, is_dir=True):
                continue
            filtered_dirs.append(d)
        dirnames[:] = filtered_dirs

        for fname in sorted(filenames):
            if fname in _DEFAULT_IGNORE_FILES:
                continue
            fpath = current / fname
            try:
                rel = str(fpath.relative_to(workdir_resolved))
                rel_posix = rel.replace('\\', '/')
            except ValueError:
                continue
            if gitignore_patterns and _is_gitignored(rel_posix, gitignore_patterns):
                continue
            result.append(fpath)
    return result


# ── File operations ──────────────────────────────────────────────────────────


async def read_file(ctx: RunContext['CodyDeps'], path: str) -> str:
    """Read file contents

    Args:
        path: Path to the file to read (relative or absolute)
    """
    full_path = _resolve_and_check(
        ctx.deps.workdir, path, allow_read_outside=True, allowed_roots=ctx.deps.allowed_roots
    )

    if not full_path.exists():
        raise ToolInvalidParams(f"File not found: {path}")

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

    # Audit log
    if ctx.deps.audit_logger:
        ctx.deps.audit_logger.log(
            event="file_write",
            tool_name="write_file",
            args_summary=f"path={path}",
            result_summary=f"Written {len(content)} bytes",
            workdir=str(ctx.deps.workdir),
        )

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

    # Audit log
    if ctx.deps.audit_logger:
        ctx.deps.audit_logger.log(
            event="file_edit",
            tool_name="edit_file",
            args_summary=f"path={path}",
            result_summary=f"Replaced text in {path}",
            workdir=str(ctx.deps.workdir),
        )

    return f"Edited {path}: replaced text"


async def list_directory(ctx: RunContext['CodyDeps'], path: str = ".") -> str:
    """List directory contents

    Args:
        path: Directory path (relative or absolute)
    """
    full_path = _resolve_and_check(
        ctx.deps.workdir, path, allow_read_outside=True, allowed_roots=ctx.deps.allowed_roots
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


# ── Search tools ─────────────────────────────────────────────────────────────


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


# ── Command execution ────────────────────────────────────────────────────────


async def exec_command(ctx: RunContext['CodyDeps'], command: str) -> str:
    """Execute shell command

    Args:
        command: Command to execute
    """
    _check_permission(ctx, "exec_command")

    # Blocked patterns: built-in baseline + user-defined via config
    _builtin_blocked = [
        'rm -rf /', 'rm -rf ~', 'rm -rf /*', 'rm -rf ~/',
        'dd if=', ':(){', 'mkfs.', '> /dev/sd',
    ]
    blocked = _builtin_blocked + ctx.deps.config.security.blocked_commands
    for pattern in blocked:
        if pattern in command:
            raise ToolPermissionDenied(f"Blocked command pattern: {pattern}")

    # Allowed commands whitelist: check every command in pipe/chain
    if ctx.deps.config.security.allowed_commands:
        for part in re.split(r'[|;&]', command):
            base_cmd = part.strip().split()[0] if part.strip() else ''
            if base_cmd and base_cmd not in ctx.deps.config.security.allowed_commands:
                raise ToolPermissionDenied(f"Command not allowed: {base_cmd}")

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=ctx.deps.workdir,
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"

        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"

        # Audit log
        if ctx.deps.audit_logger:
            ctx.deps.audit_logger.log(
                event="command_exec",
                tool_name="exec_command",
                args_summary=f"command={command}",
                result_summary=f"exit_code={result.returncode}",
                workdir=str(ctx.deps.workdir),
                success=result.returncode == 0,
            )

        return output or "[no output]"

    except subprocess.TimeoutExpired:
        if ctx.deps.audit_logger:
            ctx.deps.audit_logger.log(
                event="command_exec",
                tool_name="exec_command",
                args_summary=f"command={command}",
                result_summary="timeout",
                workdir=str(ctx.deps.workdir),
                success=False,
            )
        return "[ERROR] Command timed out after 30 seconds"
    except Exception as e:
        return f"[ERROR] {str(e)}"


# ── Skill discovery tools ───────────────────────────────────────────────────


async def list_skills(ctx: RunContext['CodyDeps']) -> str:
    """List available skills (Agent Skills open standard).

    Returns skill metadata (name + description). Use read_skill() to
    load full instructions — progressive disclosure keeps context small.
    """
    skills = ctx.deps.skill_manager.list_skills()
    if not skills:
        return "No skills available"

    lines = ["Available skills:"]
    for skill in skills:
        status = "enabled" if skill.enabled else "disabled"
        meta = ""
        if skill.compatibility:
            meta = f" ({skill.compatibility})"
        lines.append(f"[{status}] {skill.name} — {skill.description}{meta}")

    return "\n".join(lines)


async def read_skill(ctx: RunContext['CodyDeps'], skill_name: str) -> str:
    """Read full skill instructions (progressive disclosure — activated on demand).

    Args:
        skill_name: Name of the skill
    """
    skill = ctx.deps.skill_manager.get_skill(skill_name)
    if not skill:
        raise ToolInvalidParams(f"Skill not found: {skill_name}")

    return skill.instructions


# ── Sub-agent tools ──────────────────────────────────────────────────────────


async def spawn_agent(
    ctx: RunContext['CodyDeps'],
    task: str,
    agent_type: str = "generic",
) -> str:
    """Spawn a sub-agent to handle a task in the background

    Args:
        task: Task description for the sub-agent
        agent_type: Type of agent — "code", "research", "test", or "generic"
    """
    _check_permission(ctx, "spawn_agent")
    manager = ctx.deps.sub_agent_manager
    if manager is None:
        return "[ERROR] Sub-agent system not available"

    try:
        agent_id = await manager.spawn(task, agent_type)
        return f"Sub-agent spawned: {agent_id} (type={agent_type})"
    except RuntimeError as e:
        return f"[ERROR] {e}"


async def get_agent_status(ctx: RunContext['CodyDeps'], agent_id: str) -> str:
    """Check the status of a sub-agent

    Args:
        agent_id: ID of the sub-agent to check
    """
    manager = ctx.deps.sub_agent_manager
    if manager is None:
        return "[ERROR] Sub-agent system not available"

    result = manager.get_status(agent_id)
    if result is None:
        return f"[ERROR] Unknown agent: {agent_id}"

    lines = [
        f"Agent: {result.agent_id}",
        f"Status: {result.status}",
    ]
    if result.output:
        lines.append(f"Output: {result.output}")
    if result.error:
        lines.append(f"Error: {result.error}")
    if result.completed_at:
        lines.append(f"Completed: {result.completed_at}")

    return "\n".join(lines)


async def kill_agent(ctx: RunContext['CodyDeps'], agent_id: str) -> str:
    """Kill a running sub-agent

    Args:
        agent_id: ID of the sub-agent to kill
    """
    _check_permission(ctx, "kill_agent")
    manager = ctx.deps.sub_agent_manager
    if manager is None:
        return "[ERROR] Sub-agent system not available"

    killed = await manager.kill(agent_id)
    if killed:
        return f"Agent {agent_id} killed"
    return f"Agent {agent_id} is not running (already completed or unknown)"


# ── MCP tools ────────────────────────────────────────────────────────────────


async def mcp_list_tools(ctx: RunContext['CodyDeps']) -> str:
    """List tools from connected MCP servers"""
    client = ctx.deps.mcp_client
    if client is None:
        return "No MCP servers configured"

    mcp_tools = client.list_tools()
    if not mcp_tools:
        return "No MCP tools available"

    lines = ["MCP tools:"]
    for t in mcp_tools:
        lines.append(f"  {t.server_name}/{t.name} — {t.description}")

    return "\n".join(lines)


async def mcp_call(
    ctx: RunContext['CodyDeps'],
    tool_name: str,
    arguments: str = "{}",
) -> str:
    """Call an MCP tool by qualified name (server/tool)

    Args:
        tool_name: Qualified tool name, e.g. "github/create_issue"
        arguments: JSON string of tool arguments
    """
    _check_permission(ctx, "mcp_call")
    import json as _json

    client = ctx.deps.mcp_client
    if client is None:
        return "[ERROR] No MCP servers configured"

    try:
        args = _json.loads(arguments) if arguments else {}
    except _json.JSONDecodeError as e:
        return f"[ERROR] Invalid JSON arguments: {e}"

    try:
        result = await client.call_tool(tool_name, args)
        return str(result)
    except Exception as e:
        return f"[ERROR] MCP call failed: {e}"


# ── Web tools ────────────────────────────────────────────────────────────────


async def webfetch(ctx: RunContext['CodyDeps'], url: str) -> str:
    """Fetch a web page and return its content as Markdown

    Args:
        url: URL to fetch (must start with http:// or https://)
    """
    from .web import webfetch as _webfetch

    if not url.startswith(("http://", "https://")):
        return "[ERROR] URL must start with http:// or https://"

    try:
        return await _webfetch(url)
    except Exception as e:
        return f"[ERROR] Failed to fetch {url}: {e}"


async def websearch(ctx: RunContext['CodyDeps'], query: str) -> str:
    """Search the web and return results

    Args:
        query: Search query string
    """
    from .web import websearch as _websearch

    try:
        return await _websearch(query)
    except Exception as e:
        return f"[ERROR] Web search failed: {e}"


# ── LSP tools ────────────────────────────────────────────────────────────────


async def lsp_diagnostics(ctx: RunContext['CodyDeps'], file_path: str) -> str:
    """Get compiler diagnostics (errors/warnings) for a file

    Args:
        file_path: Path to the file (relative to workdir)
    """
    lsp = ctx.deps.lsp_client
    if lsp is None:
        return "[ERROR] LSP not available"

    try:
        diags = await lsp.get_diagnostics(file_path)
        if not diags:
            return f"No diagnostics for {file_path}"
        return "\n".join(str(d) for d in diags)
    except Exception as e:
        return f"[ERROR] LSP diagnostics failed: {e}"


async def lsp_definition(
    ctx: RunContext['CodyDeps'],
    file_path: str,
    line: int,
    character: int,
) -> str:
    """Go to the definition of a symbol

    Args:
        file_path: Path to the file
        line: Line number (1-based)
        character: Column number (0-based)
    """
    lsp = ctx.deps.lsp_client
    if lsp is None:
        return "[ERROR] LSP not available"

    try:
        loc = await lsp.goto_definition(file_path, line, character)
        if loc is None:
            return f"No definition found at {file_path}:{line}:{character}"
        return f"Definition: {loc}"
    except Exception as e:
        return f"[ERROR] LSP goto-definition failed: {e}"


async def lsp_references(
    ctx: RunContext['CodyDeps'],
    file_path: str,
    line: int,
    character: int,
) -> str:
    """Find all references to a symbol

    Args:
        file_path: Path to the file
        line: Line number (1-based)
        character: Column number (0-based)
    """
    lsp = ctx.deps.lsp_client
    if lsp is None:
        return "[ERROR] LSP not available"

    try:
        locations = await lsp.find_references(file_path, line, character)
        if not locations:
            return f"No references found at {file_path}:{line}:{character}"
        lines = [f"References ({len(locations)}):"]
        for loc in locations:
            lines.append(f"  {loc}")
        return "\n".join(lines)
    except Exception as e:
        return f"[ERROR] LSP find-references failed: {e}"


async def lsp_hover(
    ctx: RunContext['CodyDeps'],
    file_path: str,
    line: int,
    character: int,
) -> str:
    """Get type/documentation info for a symbol at a position

    Args:
        file_path: Path to the file
        line: Line number (1-based)
        character: Column number (0-based)
    """
    lsp = ctx.deps.lsp_client
    if lsp is None:
        return "[ERROR] LSP not available"

    try:
        info = await lsp.hover(file_path, line, character)
        if info is None:
            return f"No hover info at {file_path}:{line}:{character}"
        if info.language:
            return f"```{info.language}\n{info.content}\n```"
        return info.content
    except Exception as e:
        return f"[ERROR] LSP hover failed: {e}"


# ── File history tools ──────────────────────────────────────────────────────


async def undo_file(ctx: RunContext['CodyDeps']) -> str:
    """Undo the last file modification, restoring the file to its previous content"""
    _check_permission(ctx, "undo_file")
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
    _check_permission(ctx, "redo_file")
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


# ── Task management tools ──────────────────────────────────────────────────


async def todo_write(
    ctx: RunContext['CodyDeps'],
    todos: str,
) -> str:
    """Create or update a task list for tracking multi-step work.

    Args:
        todos: JSON string of todo items, each with "content" (str), "status" (pending/in_progress/completed)
    """
    import json as _json

    try:
        items = _json.loads(todos)
    except _json.JSONDecodeError as e:
        return f"[ERROR] Invalid JSON: {e}"

    if not isinstance(items, list):
        return "[ERROR] todos must be a JSON array"

    validated: list[dict] = []
    valid_statuses = {"pending", "in_progress", "completed"}
    for item in items:
        if not isinstance(item, dict):
            return "[ERROR] Each todo must be an object with 'content' and 'status'"
        content = item.get("content", "")
        status = item.get("status", "pending")
        if not content:
            return "[ERROR] Each todo must have non-empty 'content'"
        if status not in valid_statuses:
            return f"[ERROR] Invalid status '{status}'. Use: pending, in_progress, completed"
        validated.append({"content": content, "status": status})

    # Update the shared todo list
    if ctx.deps.todo_list is not None:
        ctx.deps.todo_list.clear()
        ctx.deps.todo_list.extend(validated)

    total = len(validated)
    done = sum(1 for t in validated if t["status"] == "completed")
    active = sum(1 for t in validated if t["status"] == "in_progress")
    return f"Todo list updated: {total} items ({done} completed, {active} in progress)"


async def todo_read(ctx: RunContext['CodyDeps']) -> str:
    """Read the current task list"""
    todo_list = ctx.deps.todo_list
    if todo_list is None or len(todo_list) == 0:
        return "No todos recorded"

    status_icons = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}
    lines = [f"Task list ({len(todo_list)} items):"]
    for i, item in enumerate(todo_list, 1):
        icon = status_icons.get(item.get("status", "pending"), "[ ]")
        lines.append(f"  {i}. {icon} {item['content']}")

    return "\n".join(lines)


# ── User interaction tools ─────────────────────────────────────────────────


async def question(
    ctx: RunContext['CodyDeps'],
    text: str,
    options: str = "",
) -> str:
    """Ask the user a structured question and wait for their answer.

    Use this when you need clarification or a decision from the user.
    The question will be displayed to the user and their response returned.

    Args:
        text: The question to ask the user
        options: Optional comma-separated list of choices (e.g. "Yes,No,Skip")
    """
    # Format the question for display
    parts = [f"[QUESTION] {text}"]
    if options:
        option_list = [o.strip() for o in options.split(",") if o.strip()]
        if option_list:
            parts.append("Options:")
            for i, opt in enumerate(option_list, 1):
                parts.append(f"  {i}. {opt}")

    # In non-interactive mode, return the question as-is for the caller to handle
    # The actual user interaction happens at the shell layer (CLI/TUI/Server)
    return "\n".join(parts)


# ── Tool registry ─────────────────────────────────────────────────────────
# Declarative tool sets. runner.py and sub_agent.py call register_tools()
# or register_sub_agent_tools() to batch-register these on Agent instances.
#
# To add a new tool:
#   1. Define the async function above.
#   2. Append it to the appropriate *_TOOLS list below.
#   3. If sub-agents should use it, add to the relevant SUB_AGENT_TOOLSETS.
#   That's it — no changes needed in runner.py or sub_agent.py.

FILE_TOOLS = [read_file, write_file, edit_file, list_directory]
SEARCH_TOOLS = [grep, glob, patch, search_files]
COMMAND_TOOLS = [exec_command]
SKILL_TOOLS = [list_skills, read_skill]
SUB_AGENT_TOOLS = [spawn_agent, get_agent_status, kill_agent]
MCP_TOOLS = [mcp_call, mcp_list_tools]
WEB_TOOLS = [webfetch, websearch]
LSP_TOOLS = [lsp_diagnostics, lsp_definition, lsp_references, lsp_hover]
FILE_HISTORY_TOOLS = [undo_file, redo_file, list_file_changes]
TODO_TOOLS = [todo_write, todo_read]
USER_TOOLS = [question]

# All tools for the main agent (MCP excluded — conditional on config)
CORE_TOOLS = (
    FILE_TOOLS + SEARCH_TOOLS + COMMAND_TOOLS + SKILL_TOOLS
    + SUB_AGENT_TOOLS + WEB_TOOLS + LSP_TOOLS
    + FILE_HISTORY_TOOLS + TODO_TOOLS + USER_TOOLS
)

# Subsets for sub-agent types.
# "research" is read-only (no write/exec) to prevent side effects.
# "test" can write files and run commands but not spawn further sub-agents.
# "code" and "generic" get the full file+search+command set.
SUB_AGENT_TOOLSETS = {
    "code": FILE_TOOLS + SEARCH_TOOLS + COMMAND_TOOLS,
    "generic": FILE_TOOLS + SEARCH_TOOLS + COMMAND_TOOLS,
    "research": [read_file, list_directory, grep, glob, search_files],
    "test": [read_file, write_file, edit_file, list_directory, grep, glob, exec_command],
}


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


def register_tools(agent, *, include_mcp: bool = False) -> None:
    """Register all core tools on an agent. Optionally include MCP tools.

    Each tool is wrapped with _with_model_retry so that ToolError exceptions
    are converted to ModelRetry, allowing the model to self-correct.
    """
    for tool_func in CORE_TOOLS:
        agent.tool(retries=2)(_with_model_retry(tool_func))
    if include_mcp:
        for tool_func in MCP_TOOLS:
            agent.tool(retries=2)(_with_model_retry(tool_func))


def register_sub_agent_tools(agent, agent_type: str) -> None:
    """Register the appropriate tool subset for a sub-agent type."""
    tool_set = SUB_AGENT_TOOLSETS.get(agent_type, SUB_AGENT_TOOLSETS["generic"])
    for tool_func in tool_set:
        agent.tool(retries=2)(_with_model_retry(tool_func))
