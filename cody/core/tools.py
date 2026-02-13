"""Core tools for Cody Agent"""

import fnmatch
import os
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic_ai import RunContext

if TYPE_CHECKING:
    from .runner import CodyDeps


def _resolve_and_check(workdir: Path, path: str) -> Path:
    """Resolve path and verify it's inside workdir. Returns resolved Path."""
    full_path = (workdir / path).resolve()
    workdir_resolved = workdir.resolve()
    if not full_path.is_relative_to(workdir_resolved):
        raise ValueError(f"Access denied: {path} is outside working directory")
    return full_path


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
        path: Path to the file to read
    """
    full_path = _resolve_and_check(ctx.deps.workdir, path)

    if not full_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    return full_path.read_text()


async def write_file(ctx: RunContext['CodyDeps'], path: str, content: str) -> str:
    """Write content to file

    Args:
        path: Path to the file
        content: Content to write
    """
    full_path = _resolve_and_check(ctx.deps.workdir, path)

    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)

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
    full_path = _resolve_and_check(ctx.deps.workdir, path)

    if not full_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    content = full_path.read_text()

    if old_text not in content:
        raise ValueError(f"Text not found in file: {old_text[:50]}...")

    new_content = content.replace(old_text, new_text, 1)
    full_path.write_text(new_content)

    return f"Edited {path}: replaced text"


async def list_directory(ctx: RunContext['CodyDeps'], path: str = ".") -> str:
    """List directory contents

    Args:
        path: Directory path (relative to workdir)
    """
    full_path = _resolve_and_check(ctx.deps.workdir, path)

    if not full_path.exists():
        raise FileNotFoundError(f"Directory not found: {path}")

    if not full_path.is_dir():
        raise ValueError(f"Not a directory: {path}")

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
        path: Directory or file to search in (relative to workdir)
        include: Optional glob to filter filenames (e.g. "*.py")
    """
    full_path = _resolve_and_check(ctx.deps.workdir, path)

    if not full_path.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    try:
        regex = re.compile(pattern)
    except re.error as e:
        raise ValueError(f"Invalid regex pattern: {e}")

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
        path: Base directory to search from (relative to workdir)
    """
    full_path = _resolve_and_check(ctx.deps.workdir, path)

    if not full_path.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    if not full_path.is_dir():
        raise ValueError(f"Not a directory: {path}")

    workdir_resolved = ctx.deps.workdir.resolve()
    gitignore_patterns = _parse_gitignore(workdir_resolved)
    results: list[str] = []
    max_results = 500

    for match in sorted(full_path.glob(pattern)):
        # Security: skip anything outside workdir
        resolved_match = match.resolve()
        if not resolved_match.is_relative_to(workdir_resolved):
            continue

        rel = match.relative_to(workdir_resolved)
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
    full_path = _resolve_and_check(ctx.deps.workdir, path)

    if not full_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    original_lines = full_path.read_text().splitlines(keepends=True)
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
                raise ValueError(f"Invalid hunk header: {line.rstrip()}")
            hunk_start = int(hunk_match.group(1)) - 1  # 0-indexed

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

    full_path.write_text("".join(result_lines))
    return f"Patched {path} successfully"


async def search_files(
    ctx: RunContext['CodyDeps'],
    query: str,
    path: str = ".",
) -> str:
    """Search for files by name (fuzzy match)

    Args:
        query: Search query to match against file names
        path: Directory to search in (relative to workdir)
    """
    full_path = _resolve_and_check(ctx.deps.workdir, path)

    if not full_path.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    if not full_path.is_dir():
        raise ValueError(f"Not a directory: {path}")

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
    # Security check
    if ctx.deps.config.security.allowed_commands:
        base_cmd = command.split()[0]
        if base_cmd not in ctx.deps.config.security.allowed_commands:
            raise PermissionError(f"Command not allowed: {base_cmd}")

    # Check for dangerous patterns
    dangerous_patterns = ['rm -rf /', 'dd if=', ':(){']
    for pattern in dangerous_patterns:
        if pattern in command:
            raise PermissionError(f"Dangerous command detected: {pattern}")

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

        return output or "[no output]"

    except subprocess.TimeoutExpired:
        return "[ERROR] Command timed out after 30 seconds"
    except Exception as e:
        return f"[ERROR] {str(e)}"


# ── Skill discovery tools ───────────────────────────────────────────────────


async def list_skills(ctx: RunContext['CodyDeps']) -> str:
    """List available skills"""
    skills = ctx.deps.skill_manager.list_skills()
    if not skills:
        return "No skills available"

    lines = ["Available skills:"]
    for skill in skills:
        status = "enabled" if skill.enabled else "disabled"
        lines.append(f"[{status}] {skill.name} - {skill.description}")

    return "\n".join(lines)


async def read_skill(ctx: RunContext['CodyDeps'], skill_name: str) -> str:
    """Read skill documentation

    Args:
        skill_name: Name of the skill
    """
    skill = ctx.deps.skill_manager.get_skill(skill_name)
    if not skill:
        raise ValueError(f"Skill not found: {skill_name}")

    return skill.documentation
