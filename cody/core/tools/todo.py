"""Task management tools — todo list."""

from pydantic_ai import RunContext

from ..deps import CodyDeps


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
