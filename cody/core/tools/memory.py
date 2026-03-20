"""Project memory tool — lets the AI persist cross-session notes."""

from pydantic_ai import RunContext

from ..deps import CodyDeps
from ..memory import CATEGORIES, MemoryEntry


async def save_memory(
    ctx: RunContext['CodyDeps'],
    category: str,
    content: str,
) -> str:
    """Save a note to project memory for future sessions.

    Use this to record important project knowledge that should persist
    across conversations, such as code conventions, architecture decisions,
    common pitfalls, or useful patterns discovered during a task.

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
