"""Sub-agent tools — spawn, status, kill."""

from pydantic_ai import RunContext

from ..deps import CodyDeps
from ._base import _check_permission


async def spawn_agent(
    ctx: RunContext['CodyDeps'],
    task: str,
    agent_type: str = "generic",
) -> str:
    """Spawn a sub-agent to handle a task in the background.

    Use sub-agents to parallelize independent work or isolate specialized tasks.
    Each sub-agent runs with its own context and returns a text result.

    Agent types and their capabilities:
      - "code": File read/write + search + shell commands. For writing or modifying code.
      - "research": Read-only (file read + search). For code analysis, pattern finding,
        no modifications.
      - "test": File read/write + shell commands. For writing tests and running test
        suites.
      - "generic": Same as code. For general-purpose tasks.

    When to use sub-agents:
      - Task has multiple independent parts that can run in parallel
      - Need to analyze different areas of the codebase simultaneously
      - Want to isolate risky operations (e.g., test execution) from the main flow

    When NOT to use sub-agents:
      - Task is simple and sequential (just do it directly)
      - Reading a specific file or searching for a known symbol (use read_file/grep
        directly)
      - Task requires results from a previous step (run sequentially instead)

    Best practices:
      - Launch multiple agents in a single turn for parallel execution
      - Provide detailed, self-contained task descriptions (agents have no shared context)
      - Use "research" type for analysis to prevent accidental file modifications
      - Check results with get_agent_status() after spawning

    Limits: max 5 concurrent agents, 300s timeout per agent.

    Args:
        task: Detailed task description. Must be self-contained — the agent has no
              context from the current conversation.
        agent_type: "code", "research", "test", or "generic"
    """
    await _check_permission(ctx, "spawn_agent")
    manager = ctx.deps.sub_agent_manager
    if manager is None:
        return "[ERROR] Sub-agent system not available"

    try:
        agent_id = await manager.spawn(task, agent_type)
        return f"Sub-agent spawned: {agent_id} (type={agent_type})"
    except RuntimeError as e:
        return f"[ERROR] {e}"


async def get_agent_status(ctx: RunContext['CodyDeps'], agent_id: str) -> str:
    """Check the status of a sub-agent

    Args:
        agent_id: ID of the sub-agent to check
    """
    manager = ctx.deps.sub_agent_manager
    if manager is None:
        return "[ERROR] Sub-agent system not available"

    result = manager.get_status(agent_id)
    if result is None:
        return f"[ERROR] Unknown agent: {agent_id}"

    lines = [
        f"Agent: {result.agent_id}",
        f"Status: {result.status}",
    ]
    if result.output:
        lines.append(f"Output: {result.output}")
    if result.error:
        lines.append(f"Error: {result.error}")
    if result.completed_at:
        lines.append(f"Completed: {result.completed_at}")

    return "\n".join(lines)


async def kill_agent(ctx: RunContext['CodyDeps'], agent_id: str) -> str:
    """Kill a running sub-agent

    Args:
        agent_id: ID of the sub-agent to kill
    """
    await _check_permission(ctx, "kill_agent")
    manager = ctx.deps.sub_agent_manager
    if manager is None:
        return "[ERROR] Sub-agent system not available"

    killed = await manager.kill(agent_id)
    if killed:
        return f"Agent {agent_id} killed"
    return f"Agent {agent_id} is not running (already completed or unknown)"
