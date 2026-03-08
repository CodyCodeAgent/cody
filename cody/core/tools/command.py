"""Command execution tool."""

import re
import subprocess

from pydantic_ai import RunContext

from ..deps import CodyDeps
from ..errors import ToolPermissionDenied
from ._base import _audit_tool_call, _check_permission

# Regex-based blocked command patterns — handles whitespace variations and
# argument reordering that simple substring matching would miss.
_MAX_COMMAND_LENGTH = 4096

_BLOCKED_COMMAND_PATTERNS = [
    re.compile(r'rm\s+-[a-z]*r[a-z]*f[a-z]*\s+/'),    # rm -rf /
    re.compile(r'rm\s+-[a-z]*f[a-z]*r[a-z]*\s+/'),    # rm -fr /
    re.compile(r'rm\s+-r\s+-f\s+/'),                    # rm -r -f /
    re.compile(r'rm\s+-f\s+-r\s+/'),                    # rm -f -r /
    re.compile(r'rm\s+-[a-z]*r[a-z]*f[a-z]*\s+~'),    # rm -rf ~
    re.compile(r'rm\s+-[a-z]*f[a-z]*r[a-z]*\s+~'),    # rm -fr ~
    re.compile(r'rm\s+-[a-z]*r[a-z]*f[a-z]*\s+/\*'),  # rm -rf /*
    re.compile(r'rm\s+-[a-z]*f[a-z]*r[a-z]*\s+/\*'),  # rm -fr /*
    re.compile(r'dd\s+if='),                             # dd if=
    re.compile(r':\(\)\s*\{'),                           # fork bomb
    re.compile(r'mkfs\.'),                               # mkfs
    re.compile(r'>\s*/dev/sd'),                          # overwrite disk
    re.compile(r'\$\('),                                 # command substitution $(...)
    re.compile(r'`[^`]+`'),                              # backtick command substitution
    re.compile(r'\beval\b'),                             # eval
    re.compile(r'\bexec\b'),                             # exec
    re.compile(r'base64\s+.*\|\s*(sh|bash|zsh)'),       # base64 decode piped to shell
]


async def exec_command(ctx: RunContext['CodyDeps'], command: str, timeout: int = 0) -> str:
    """Execute shell command

    Args:
        command: Command to execute
        timeout: Timeout in seconds (0 = use config default)
    """
    _check_permission(ctx, "exec_command")

    # Reject excessively long commands
    if len(command) > _MAX_COMMAND_LENGTH:
        raise ToolPermissionDenied(
            f"Command too long ({len(command)} chars, max {_MAX_COMMAND_LENGTH})"
        )

    # Normalize whitespace for consistent pattern matching
    normalized = re.sub(r'\s+', ' ', command.strip())
    # Check regex-based built-in blocked patterns
    for pattern in _BLOCKED_COMMAND_PATTERNS:
        if pattern.search(normalized):
            raise ToolPermissionDenied("Blocked command pattern detected")
    # User-defined blocked commands (substring match, backward compatible)
    for user_pattern in ctx.deps.config.security.blocked_commands:
        if user_pattern in normalized:
            raise ToolPermissionDenied(f"Blocked command pattern: {user_pattern}")

    # Allowed commands whitelist: check every command in pipe/chain
    if ctx.deps.config.security.allowed_commands:
        for part in re.split(r'[|;&]', command):
            base_cmd = part.strip().split()[0] if part.strip() else ''
            if base_cmd and base_cmd not in ctx.deps.config.security.allowed_commands:
                raise ToolPermissionDenied(f"Command not allowed: {base_cmd}")

    effective_timeout = timeout or ctx.deps.config.security.command_timeout

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=ctx.deps.workdir,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
        )

        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"

        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"

        _audit_tool_call(
            ctx, "command_exec", "exec_command",
            f"command={command}", f"exit_code={result.returncode}",
            success=result.returncode == 0,
        )

        return output or "[no output]"

    except subprocess.TimeoutExpired:
        _audit_tool_call(
            ctx, "command_exec", "exec_command",
            f"command={command}", "timeout", success=False,
        )
        return f"[ERROR] Command timed out after {effective_timeout} seconds"
    except Exception as e:
        return f"[ERROR] {str(e)}"
