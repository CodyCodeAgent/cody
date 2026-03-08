"""Skill discovery tools."""

from pydantic_ai import RunContext

from ..deps import CodyDeps
from ..errors import ToolInvalidParams


async def list_skills(ctx: RunContext['CodyDeps']) -> str:
    """List available skills (Agent Skills open standard).

    Returns skill metadata (name + description). Use read_skill() to
    load full instructions — progressive disclosure keeps context small.
    """
    skills = ctx.deps.skill_manager.list_skills()
    if not skills:
        return "No skills available"

    lines = ["Available skills:"]
    for skill in skills:
        status = "enabled" if skill.enabled else "disabled"
        meta = ""
        if skill.compatibility:
            meta = f" ({skill.compatibility})"
        lines.append(f"[{status}] {skill.name} — {skill.description}{meta}")

    return "\n".join(lines)


async def read_skill(ctx: RunContext['CodyDeps'], skill_name: str) -> str:
    """Read full skill instructions (progressive disclosure — activated on demand).

    Args:
        skill_name: Name of the skill
    """
    skill = ctx.deps.skill_manager.get_skill(skill_name)
    if not skill:
        raise ToolInvalidParams(f"Skill not found: {skill_name}")

    return skill.instructions
