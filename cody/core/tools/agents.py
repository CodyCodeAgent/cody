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

    IMPORTANT: You should actively use sub-agents whenever a task can be decomposed
    into 2+ independent parts. Parallel execution is significantly faster. Spawn
    multiple agents in a single turn — do NOT do them one by one sequentially.

    Examples:
      - "Add tests for auth and billing" → spawn 2 test agents in one turn
      - "Refactor logging in api/ and workers/" → spawn 2 code agents
      - "Analyze frontend and backend architecture" → spawn 2 research agents
      - "Add error handling to 5 service files" → spawn up to 5 code agents

    Agent types:
      - "code" / "generic": File read/write + search + shell. For writing/modifying code.
      - "research": Read-only (file read + search). For analysis without side effects.
      - "test": File read/write + shell. For writing and running tests.

    Only do it yourself (no sub-agent) when:
      - The task is a single simple step (one file read, one grep, one small edit)
      - Steps are strictly sequential (step B depends on step A's output)

    Best practices:
      - Provide detailed, self-contained task descriptions (agents have NO shared context
        with the current conversation — include file paths, requirements, constraints)
      - Use "research" type for read-only analysis to prevent accidental modifications
      - After spawning, call get_agent_status() to collect results

    Limits: max 5 concurrent agents, 300s timeout per agent.

    Args:
        task: Detailed, self-contained task description. Include all relevant file paths,
              requirements, and context — the agent cannot see your conversation history.
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


async def resume_agent(ctx: RunContext['CodyDeps'], agent_id: str) -> str:
    """Resume a completed/failed/timed-out sub-agent.

    Re-spawns a new agent with the original task plus previous output/error
    as context, so the model can continue where the previous agent left off.

    Use this when a sub-agent timed out, failed with a recoverable error,
    or completed partially and you need it to continue.

    Args:
        agent_id: ID of the sub-agent to resume
    """
    await _check_permission(ctx, "resume_agent")
    manager = ctx.deps.sub_agent_manager
    if manager is None:
        return "[ERROR] Sub-agent system not available"

    try:
        new_id = await manager.resume(agent_id)
        prev = manager.get_status(agent_id)
        return (
            f"Resumed agent {agent_id} → new agent {new_id}\n"
            f"Previous status: {prev.status if prev else 'unknown'}"
        )
    except (ValueError, RuntimeError) as e:
        return f"[ERROR] {e}"


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
