"""LSP (Language Server Protocol) tools."""

from pydantic_ai import RunContext

from ..deps import CodyDeps


async def lsp_diagnostics(ctx: RunContext['CodyDeps'], file_path: str) -> str:
    """Get compiler diagnostics (errors/warnings) for a file

    Args:
        file_path: Path to the file (relative to workdir)
    """
    lsp = ctx.deps.lsp_client
    if lsp is None:
        return "[ERROR] LSP not available"

    diags = await lsp.get_diagnostics(file_path)
    if not diags:
        return f"No diagnostics for {file_path}"
    return "\n".join(str(d) for d in diags)


async def lsp_definition(
    ctx: RunContext['CodyDeps'],
    file_path: str,
    line: int,
    character: int,
) -> str:
    """Go to the definition of a symbol

    Args:
        file_path: Path to the file
        line: Line number (1-based)
        character: Column number (0-based)
    """
    lsp = ctx.deps.lsp_client
    if lsp is None:
        return "[ERROR] LSP not available"

    loc = await lsp.goto_definition(file_path, line, character)
    if loc is None:
        return f"No definition found at {file_path}:{line}:{character}"
    return f"Definition: {loc}"


async def lsp_references(
    ctx: RunContext['CodyDeps'],
    file_path: str,
    line: int,
    character: int,
) -> str:
    """Find all references to a symbol

    Args:
        file_path: Path to the file
        line: Line number (1-based)
        character: Column number (0-based)
    """
    lsp = ctx.deps.lsp_client
    if lsp is None:
        return "[ERROR] LSP not available"

    locations = await lsp.find_references(file_path, line, character)
    if not locations:
        return f"No references found at {file_path}:{line}:{character}"
    lines = [f"References ({len(locations)}):"]
    for loc in locations:
        lines.append(f"  {loc}")
    return "\n".join(lines)


async def lsp_hover(
    ctx: RunContext['CodyDeps'],
    file_path: str,
    line: int,
    character: int,
) -> str:
    """Get type/documentation info for a symbol at a position

    Args:
        file_path: Path to the file
        line: Line number (1-based)
        character: Column number (0-based)
    """
    lsp = ctx.deps.lsp_client
    if lsp is None:
        return "[ERROR] LSP not available"

    info = await lsp.hover(file_path, line, character)
    if info is None:
        return f"No hover info at {file_path}:{line}:{character}"
    if info.language:
        return f"```{info.language}\n{info.content}\n```"
    return info.content
