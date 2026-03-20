"""Project memory tool — lets the AI persist cross-session notes."""

from pydantic_ai import RunContext

from ..deps import CodyDeps
from ..memory import CATEGORIES, MemoryEntry


async def save_memory(
    ctx: RunContext['CodyDeps'],
    category: str,
    content: str,
) -> str:
    """Save a project-specific note that will be injected into the system prompt of future sessions.

    Call this PROACTIVELY when you discover something noteworthy during a task — don't wait to be asked.

    When to use:
      - You figured out a non-obvious project convention (e.g. test naming, import style)
      - You found a tricky bug or pitfall that future tasks should avoid
      - You identified a recurring pattern or utility in the codebase
      - An architecture or tooling decision was made during the conversation

    When NOT to use:
      - The information is already in CODY.md or project docs
      - It's trivial or obvious (e.g. "this project uses Python")
      - It's task-specific and won't help future sessions

    Categories and examples:
      - "conventions": "Tests use @pytest.mark.asyncio with auto mode, no need to add it per-test"
      - "patterns": "All tools follow the pattern: async def tool(ctx: RunContext[CodyDeps], ...) -> str"
      - "issues": "LSP servers fail silently if pyright is not installed — check with `which pyright` first"
      - "decisions": "Chose SQLite over PostgreSQL for session store to keep zero-config deployment"

    Keep each entry concise — one idea per call. Prefer actionable notes over observations.

    Args:
        category: One of "conventions", "patterns", "issues", "decisions".
        content: The note to remember (concise, one idea per entry).
    """
    store = ctx.deps.memory_store
    if store is None:
        return "[ERROR] Project memory is not available"

    if category not in CATEGORIES:
        return f"[ERROR] Invalid category '{category}'. Use: {', '.join(CATEGORIES)}"

    if not content.strip():
        return "[ERROR] Content must not be empty"

    entry = MemoryEntry(content=content.strip())
    await store.add_entries(category, [entry])
    counts = store.count()
    return f"Saved to '{category}' ({counts.get(category, 0)} entries total)"
