"""Load and merge CODY.md project instructions.

Cody reads CODY.md files at the start of every session to understand
project-specific context, conventions, and architecture.

Discovery order (both loaded and merged if present):
  1. ~/.cody/CODY.md  — global user-level instructions
  2. <workdir>/CODY.md — project-level instructions

Project-level instructions are appended after global ones, so they take
visual precedence in the merged output. Neither file is required.

Generation:
  generate_project_instructions() uses an AgentRunner to let AI explore
  the project (list_directory / read_file / glob) and produce CODY.md
  content automatically. Used by `cody init`.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .config import Config

CODY_MD_FILENAME = "CODY.md"

# ---------------------------------------------------------------------------
# Template written by `cody init`
# ---------------------------------------------------------------------------

CODY_MD_TEMPLATE = """\
# CODY.md — Project Instructions

<!--
  This file is read by Cody at the start of every session.
  Use it to record project conventions, architecture notes, and any
  context that helps Cody work more effectively in this codebase.

  Tip: keep it concise — Cody reads it every time.
-->

## Project Overview

<!-- Briefly describe what this project is and does. -->


## Architecture

<!-- Key components, file structure, data-flow notes. -->


## Conventions

<!-- Coding style, branch naming, commit message format, etc. -->


## Development Commands

<!-- How to install, test, lint, run locally. -->

```bash
# Install
# ...

# Test
# ...

# Lint
# ...
```

## Important Notes

<!-- Gotchas, known issues, or anything Cody must always keep in mind. -->
"""


# ---------------------------------------------------------------------------
# Loading logic
# ---------------------------------------------------------------------------


def load_project_instructions(workdir: Path) -> Optional[str]:
    """Load and merge global + project CODY.md contents.

    Returns a single merged string, or ``None`` if neither file exists or
    both are empty.

    Merge format::

        <global content>

        ---

        <project content>

    The separator makes it easy to distinguish the two layers when reading
    the system prompt in debug output.
    """
    parts: list[str] = []

    global_path = Path.home() / ".cody" / CODY_MD_FILENAME
    _maybe_load(global_path, parts)

    project_path = workdir / CODY_MD_FILENAME
    _maybe_load(project_path, parts)

    if not parts:
        return None
    return "\n\n---\n\n".join(parts)


def _maybe_load(path: Path, parts: list) -> None:
    """Append non-empty file content to *parts* if the file exists."""
    if not path.is_file():
        return
    try:
        content = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return
    if content:
        parts.append(content)


# ---------------------------------------------------------------------------
# AI-powered generation (used by `cody init`)
# ---------------------------------------------------------------------------

_GENERATE_PROMPT = """\
You are helping initialize a Cody project. Analyze the current project \
directory and generate a CODY.md file that will be read at the start of \
every Cody session to give useful project context.

Steps:
1. Use list_directory and glob to understand the project structure.
2. Read the most informative files (README, pyproject.toml, package.json, \
Cargo.toml, go.mod, Makefile, main entry points, CI config, etc.) — \
skip binary files, lock files, and generated code.
3. Output ONLY the CODY.md markdown content. Do not write any files.

The CODY.md must use this exact structure (fill in each section based on \
what you find; omit a section only if truly irrelevant):

```
# CODY.md — Project Instructions

## Project Overview

<what this project is and does, 2-4 sentences>

## Architecture

<key components, important directories, data-flow summary>

## Conventions

<coding style, language version, naming rules, branch/commit format, \
linting tools, etc.>

## Development Commands

```bash
# Install
...

# Test
...

# Lint / Format
...

# Run / Start
...
```

## Important Notes

<gotchas, known pitfalls, decisions Cody must always respect>
```

Keep it concise (aim for 80-150 lines). Focus on what is most useful for \
an AI coding assistant working in this codebase. Output only the markdown, \
starting with the `# CODY.md` heading.
"""


async def generate_project_instructions(workdir: Path, config: "Config") -> str:
    """Analyze the project with AI and return generated CODY.md content.

    Uses AgentRunner (with full file-exploration tools) to let the model
    read the project structure and produce a filled-in CODY.md.

    Raises any exception from AgentRunner so callers can fall back to the
    static template when no API key is configured or network is unavailable.

    Note: AgentRunner imports from this module, so we use a lazy import
    here to avoid a circular dependency (same pattern as sub_agent.py).
    """
    # Lazy import to break circular dependency: runner → project_instructions
    from .runner import AgentRunner  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

    runner = AgentRunner(config=config, workdir=workdir)
    result = await runner.run(_GENERATE_PROMPT)
    content = result.output.strip()

    # Sanity-check: if the model returned empty output, raise so the caller
    # falls back to the static template.
    if not content:
        raise ValueError("AI returned empty CODY.md content")

    return content
