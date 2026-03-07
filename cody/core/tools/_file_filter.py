"""File filtering — binary detection, gitignore support, default ignores."""

import fnmatch
import os
from pathlib import Path

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
