"""Load and merge CODY.md project instructions.

Cody reads CODY.md files at the start of every session to understand
project-specific context, conventions, and architecture.

Discovery order (both loaded and merged if present):
  1. ~/.cody/CODY.md  — global user-level instructions
  2. <workdir>/CODY.md — project-level instructions

Project-level instructions are appended after global ones, so they take
visual precedence in the merged output. Neither file is required.
"""

from pathlib import Path
from typing import Optional

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
