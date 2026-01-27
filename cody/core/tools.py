"""Core tools for Cody Agent"""

import subprocess
from pathlib import Path
from pydantic_ai import RunContext
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .runner import CodyDeps


async def read_file(ctx: RunContext['CodyDeps'], path: str) -> str:
    """Read file contents
    
    Args:
        path: Path to the file to read
    """
    full_path = Path(ctx.deps.workdir) / path
    
    # Security check
    if not full_path.is_relative_to(ctx.deps.workdir):
        raise ValueError(f"Access denied: {path} is outside working directory")
    
    if not full_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    return full_path.read_text()


async def write_file(ctx: RunContext['CodyDeps'], path: str, content: str) -> str:
    """Write content to file
    
    Args:
        path: Path to the file
        content: Content to write
    """
    full_path = Path(ctx.deps.workdir) / path
    
    # Security check
    if not full_path.is_relative_to(ctx.deps.workdir):
        raise ValueError(f"Access denied: {path} is outside working directory")
    
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)
    
    return f"Written {len(content)} bytes to {path}"


async def edit_file(
    ctx: RunContext['CodyDeps'], 
    path: str, 
    old_text: str, 
    new_text: str
) -> str:
    """Edit file by replacing exact text
    
    Args:
        path: Path to the file
        old_text: Exact text to replace
        new_text: New text
    """
    full_path = Path(ctx.deps.workdir) / path
    
    # Security check
    if not full_path.is_relative_to(ctx.deps.workdir):
        raise ValueError(f"Access denied: {path} is outside working directory")
    
    if not full_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    content = full_path.read_text()
    
    if old_text not in content:
        raise ValueError(f"Text not found in file: {old_text[:50]}...")
    
    new_content = content.replace(old_text, new_text, 1)
    full_path.write_text(new_content)
    
    return f"Edited {path}: replaced text"


async def list_directory(ctx: RunContext['CodyDeps'], path: str = ".") -> str:
    """List directory contents
    
    Args:
        path: Directory path (relative to workdir)
    """
    full_path = Path(ctx.deps.workdir) / path
    
    # Security check
    if not full_path.is_relative_to(ctx.deps.workdir):
        raise ValueError(f"Access denied: {path} is outside working directory")
    
    if not full_path.exists():
        raise FileNotFoundError(f"Directory not found: {path}")
    
    if not full_path.is_dir():
        raise ValueError(f"Not a directory: {path}")
    
    items = []
    for item in sorted(full_path.iterdir()):
        prefix = "📁" if item.is_dir() else "📄"
        items.append(f"{prefix} {item.name}")
    
    return "\n".join(items)


async def exec_command(ctx: RunContext['CodyDeps'], command: str) -> str:
    """Execute shell command
    
    Args:
        command: Command to execute
    """
    # Security check
    if ctx.deps.config.security.allowed_commands:
        base_cmd = command.split()[0]
        if base_cmd not in ctx.deps.config.security.allowed_commands:
            raise PermissionError(f"Command not allowed: {base_cmd}")
    
    # Check for dangerous patterns
    dangerous_patterns = ['rm -rf /', 'dd if=', ':(){']
    for pattern in dangerous_patterns:
        if pattern in command:
            raise PermissionError(f"Dangerous command detected: {pattern}")
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=ctx.deps.workdir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        
        return output or "[no output]"
    
    except subprocess.TimeoutExpired:
        return "[ERROR] Command timed out after 30 seconds"
    except Exception as e:
        return f"[ERROR] {str(e)}"


# Skill discovery tools
async def list_skills(ctx: RunContext['CodyDeps']) -> str:
    """List available skills"""
    skills = ctx.deps.skill_manager.list_skills()
    if not skills:
        return "No skills available"
    
    lines = ["Available skills:"]
    for skill in skills:
        status = "✅" if skill.enabled else "⏸️"
        lines.append(f"{status} {skill.name} - {skill.description}")
    
    return "\n".join(lines)


async def read_skill(ctx: RunContext['CodyDeps'], skill_name: str) -> str:
    """Read skill documentation
    
    Args:
        skill_name: Name of the skill
    """
    skill = ctx.deps.skill_manager.get_skill(skill_name)
    if not skill:
        raise ValueError(f"Skill not found: {skill_name}")
    
    return skill.documentation
