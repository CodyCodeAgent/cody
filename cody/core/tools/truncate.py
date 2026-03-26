"""Tool output truncation.

Prevents individual tool outputs from consuming excessive context window
tokens. Outputs exceeding the character limit are truncated; the full
content is written to a temporary file so the model can still read
specific sections if needed.

Temp files are stored in ``<workdir>/.cody/tmp/`` (created automatically)
and can be cleaned up via :func:`cleanup_truncation_files`.
"""

import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Default limits — overridden by Config.truncation.*
DEFAULT_MAX_OUTPUT_CHARS = 120_000   # ~30K tokens (4 chars/token estimate)
DEFAULT_ENABLED = True

# Subdirectory under workdir for truncation temp files.
_TRUNCATION_DIR = ".cody/tmp"


def _ensure_truncation_dir(workdir: Path | None) -> Path | None:
    """Return the truncation temp directory, creating it if needed."""
    if workdir is None:
        return None
    d = workdir / _TRUNCATION_DIR
    try:
        d.mkdir(parents=True, exist_ok=True)
        # Add to .gitignore if not already present
        gitignore = workdir / ".cody" / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("tmp/\n")
    except OSError:
        return None
    return d


def truncate_output(
    output: str,
    tool_name: str = "",
    *,
    max_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    workdir: Path | None = None,
) -> str:
    """Truncate tool output if it exceeds *max_chars*.

    When truncated, the full output is saved to a temporary file and
    a pointer is appended so the model can ``read_file()`` the rest.

    Returns the (possibly truncated) output string.
    """
    if len(output) <= max_chars:
        return output

    original_len = len(output)

    # Write full output to .cody/tmp/ (or system temp as fallback).
    suffix = f".{tool_name}.txt" if tool_name else ".tool_output.txt"
    truncation_dir = _ensure_truncation_dir(workdir)
    try:
        fd = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=suffix,
            prefix="cody_truncated_",
            dir=str(truncation_dir) if truncation_dir else None,
            delete=False,
        )
        fd.write(output)
        fd.close()
        saved_path = fd.name
    except OSError:
        # If we can't write the temp file, just truncate without a pointer.
        saved_path = None
        logger.warning("Failed to write truncated output to temp file for %s", tool_name)

    truncated = output[:max_chars]
    trailer = (
        f"\n\n... [OUTPUT TRUNCATED — {original_len:,} chars total, "
        f"showing first {max_chars:,}]"
    )
    if saved_path:
        trailer += (
            f"\nFull output saved to: {saved_path}\n"
            f"IMPORTANT: Do NOT re-run this command. "
            f"Use read_file('{saved_path}', offset=N, limit=M) to read remaining sections."
        )

    return truncated + trailer


def cleanup_truncation_files(workdir: Path) -> int:
    """Remove all truncation temp files from ``.cody/tmp/``.

    Returns the number of files removed.
    """
    d = workdir / _TRUNCATION_DIR
    if not d.exists():
        return 0
    count = 0
    for f in d.glob("cody_truncated_*"):
        try:
            f.unlink()
            count += 1
        except OSError:
            pass
    return count
