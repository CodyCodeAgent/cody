"""Custom tools and prompt customization examples for Cody SDK.

Shows how to:
- Register custom tool functions via .tool()
- Replace the default system prompt via .system_prompt()
- Append extra instructions via .extra_system_prompt()
"""

import asyncio

from pydantic_ai import RunContext

from cody.core.deps import CodyDeps
from cody.sdk import Cody


# ── Custom tool functions ──────────────────────────────────────────────────


async def lookup_user(ctx: RunContext[CodyDeps], username: str) -> str:
    """Look up a user by username and return their profile info.

    The docstring becomes the tool description visible to the model.
    """
    # In a real app, this would query a database or API
    fake_db = {
        "alice": "Alice Wang — Backend Engineer, Team Infra",
        "bob": "Bob Li — Frontend Engineer, Team Web",
    }
    return fake_db.get(username, f"User '{username}' not found")


async def get_weather(ctx: RunContext[CodyDeps], city: str) -> str:
    """Get current weather for a city."""
    # Placeholder — replace with a real API call
    return f"Weather in {city}: 22°C, partly cloudy"


# ── Example 1: Register custom tools ──────────────────────────────────────


async def custom_tools_example():
    """Register custom tools so the agent can call them."""
    client = (
        Cody()
        .workdir(".")
        .tool(lookup_user)
        .tool(get_weather)
        .build()
    )

    async with client:
        result = await client.run("Who is alice? Also, what's the weather in Beijing?")
        print(result.output)


# ── Example 2: Custom system prompt ───────────────────────────────────────


async def custom_system_prompt_example():
    """Replace the default persona with a custom one.

    .system_prompt() replaces only the base persona. CODY.md project
    instructions, project memory, and skills are still appended.
    """
    client = (
        Cody()
        .workdir(".")
        .system_prompt(
            "You are a security-focused code review agent. "
            "Always check for OWASP Top 10 vulnerabilities. "
            "Report findings in a structured format."
        )
        .build()
    )

    async with client:
        result = await client.run("Review the code in this project for security issues")
        print(result.output)


# ── Example 3: Extra system prompt ────────────────────────────────────────


async def extra_system_prompt_example():
    """Append additional instructions without replacing the default persona.

    .extra_system_prompt() adds to the built-in prompt instead of replacing it.
    Use this for injecting business context or run-specific instructions.
    """
    client = (
        Cody()
        .workdir(".")
        .extra_system_prompt(
            "Always respond in Chinese. "
            "When writing code comments, also use Chinese."
        )
        .build()
    )

    async with client:
        result = await client.run("Explain the project structure")
        print(result.output)


# ── Example 4: Combine custom tools + prompt ──────────────────────────────


async def combined_example():
    """Combine custom tools with a custom persona."""
    client = (
        Cody()
        .workdir(".")
        .system_prompt(
            "You are a DevOps assistant. Use available tools to gather "
            "information and help the user manage their infrastructure."
        )
        .tool(lookup_user)
        .tool(get_weather)
        .build()
    )

    async with client:
        result = await client.run(
            "Find out who alice is and check the weather in her city"
        )
        print(result.output)


if __name__ == "__main__":
    asyncio.run(custom_tools_example())
