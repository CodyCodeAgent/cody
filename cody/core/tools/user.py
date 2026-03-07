"""User interaction tools."""

from pydantic_ai import RunContext

from ..deps import CodyDeps


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
