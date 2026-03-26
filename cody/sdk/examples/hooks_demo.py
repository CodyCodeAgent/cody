"""Tool hooks (step hooks) examples for Cody SDK.

Shows how to:
- Use before_tool hooks to log, modify, or reject tool calls
- Use after_tool hooks to transform tool results
- Chain multiple hooks together
"""

import asyncio
import os

from cody.sdk import Cody


# ── Hook functions ─────────────────────────────────────────────────────────


async def log_tool_call(tool_name: str, args: dict) -> dict:
    """before_tool hook: Log every tool call.

    Return args to proceed, or None to reject the call.
    """
    print(f"  [hook] → Calling {tool_name}({args})")
    return args  # Return args to proceed


async def block_dangerous_commands(tool_name: str, args: dict) -> dict | None:
    """before_tool hook: Block dangerous shell commands.

    Return None to reject the call — the model will see a retry message
    and can self-correct.
    """
    if tool_name == "exec_command":
        cmd = args.get("command", "")
        blocked = ["rm -rf", "git push --force", "DROP TABLE"]
        for pattern in blocked:
            if pattern in cmd:
                print(f"  [hook] ✕ BLOCKED: {tool_name}({cmd!r})")
                return None  # Reject — model gets a retry message
    return args


async def redact_secrets(tool_name: str, args: dict, result: str) -> str:
    """after_tool hook: Redact sensitive values from tool output."""
    secret = os.environ.get("SECRET_KEY", "")
    if secret and secret in result:
        result = result.replace(secret, "***REDACTED***")
        print(f"  [hook] ← Redacted secret from {tool_name} output")
    return result


async def truncate_long_results(tool_name: str, args: dict, result: str) -> str:
    """after_tool hook: Truncate very long tool output to save tokens."""
    max_len = 5000
    if len(result) > max_len:
        truncated = result[:max_len] + f"\n... (truncated, {len(result)} chars total)"
        print(f"  [hook] ← Truncated {tool_name} output: {len(result)} → {max_len}")
        return truncated
    return result


# ── Example 1: Logging hook ───────────────────────────────────────────────


async def logging_hook_example():
    """Log all tool calls with a before_tool hook."""
    client = (
        Cody()
        .workdir(".")
        .before_tool(log_tool_call)
        .build()
    )

    async with client:
        result = await client.run("List the Python files in this project")
        print(f"\nOutput: {result.output[:200]}")


# ── Example 2: Security hook (reject dangerous calls) ─────────────────────


async def security_hook_example():
    """Block dangerous commands with a before_tool hook.

    When a hook returns None, the tool call is rejected and the model
    receives a retry message. The model can then self-correct and try
    a safer approach.
    """
    client = (
        Cody()
        .workdir(".")
        .before_tool(block_dangerous_commands)
        .build()
    )

    async with client:
        # The agent might try dangerous commands, but they'll be blocked
        result = await client.run("Clean up all temporary files in /tmp")
        print(f"\nOutput: {result.output[:200]}")


# ── Example 3: After-tool hooks ───────────────────────────────────────────


async def after_hook_example():
    """Transform tool output with after_tool hooks."""
    client = (
        Cody()
        .workdir(".")
        .after_tool(redact_secrets)
        .after_tool(truncate_long_results)
        .build()
    )

    async with client:
        result = await client.run("Read the configuration files in this project")
        print(f"\nOutput: {result.output[:200]}")


# ── Example 4: Combined hooks ─────────────────────────────────────────────


async def combined_hooks_example():
    """Chain multiple before and after hooks together.

    Multiple hooks execute in registration order:
    - before hooks: log → block_dangerous → (tool executes)
    - after hooks:  redact → truncate
    """
    client = (
        Cody()
        .workdir(".")
        .before_tool(log_tool_call)
        .before_tool(block_dangerous_commands)
        .after_tool(redact_secrets)
        .after_tool(truncate_long_results)
        .build()
    )

    async with client:
        result = await client.run("Analyze the project structure and config")
        print(f"\nOutput: {result.output[:200]}")


if __name__ == "__main__":
    asyncio.run(logging_hook_example())
