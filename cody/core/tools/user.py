"""User interaction tools."""

from pydantic_ai import RunContext

from ..deps import CodyDeps
from ..interaction import InteractionRequest


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
    option_list = [o.strip() for o in options.split(",") if o.strip()] if options else []

    handler = ctx.deps.interaction_handler
    if handler is not None:
        request = InteractionRequest(
            kind="question",
            prompt=text,
            options=option_list,
        )
        response = await handler(request)
        if response.action == "answer" and response.content:
            return response.content
        # approve / reject — return the action as feedback to the AI
        return f"[User {response.action}]"

    # Fallback: format question for display (legacy non-interactive mode)
    parts = [f"[QUESTION] {text}"]
    if option_list:
        parts.append("Options:")
        for i, opt in enumerate(option_list, 1):
            parts.append(f"  {i}. {opt}")
    return "\n".join(parts)
