"""Shared utilities for CLI and TUI layers.

Contains presentation helpers that both CLI and TUI need but that don't
belong in core/ (they are purely UI concerns).
"""

from pathlib import Path

# ── Spinner / formatting ─────────────────────────────────────────────────────

SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def truncate_repr(value: object, max_len: int = 120) -> str:
    """Truncate repr of a value to *max_len* characters."""
    s = repr(value)
    if len(s) <= max_len:
        return s
    return s[:max_len] + f"...({len(s)} chars)"


def format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as e.g. '5s' or '1m 23s'."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m {s % 60}s"


# ── Compact event message ────────────────────────────────────────────────────

def compact_message(original: int, compacted: int, tokens_saved: int) -> str:
    """Build the context-compaction notification string (Chinese)."""
    return (
        f"⚡ 上下文已压缩：{original} → {compacted} 条消息，"
        f"节省约 ~{tokens_saved} tokens"
    )


# ── Session helpers ──────────────────────────────────────────────────────────

def auto_title(text: str, max_len: int = 60) -> str:
    """Derive a session title from the first user message."""
    title = text[:max_len].strip()
    if len(text) > max_len:
        title += "..."
    return title


def format_session_line(
    sid: str, title: str, count: int, updated_at: str,
    current_id: str = "",
) -> str:
    """Format a single session-list row (shared by CLI /sessions and TUI)."""
    marker = " << current" if sid == current_id else ""
    return f"  {sid}  {title[:40]:<40}  {count} msgs  {updated_at[:10]}{marker}"


# ── Config path resolution ───────────────────────────────────────────────────

def resolve_config_path() -> Path:
    """Find the config.json path: project-local first, then global."""
    local = Path.cwd() / ".cody" / "config.json"
    if local.exists():
        return local
    global_path = Path.home() / ".cody" / "config.json"
    global_path.parent.mkdir(parents=True, exist_ok=True)
    return global_path
