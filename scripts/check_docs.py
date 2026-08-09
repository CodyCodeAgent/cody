#!/usr/bin/env python3
"""Validate Cody's repository documentation against public code surfaces."""

from __future__ import annotations

import ast
import re
from pathlib import Path
import sys
import textwrap


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".venv", "node_modules", "dist"}
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
SECRET_RE = re.compile(r"sk-[A-Za-z0-9_-]{20,}")
PYTHON_FENCE_RE = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)


def markdown_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if not EXCLUDED_PARTS.intersection(path.relative_to(ROOT).parts)
    )


def check_local_links(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            target = match.group(1).strip().split()[0].strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            relative = target.split("#", 1)[0]
            if relative and not (path.parent / relative).resolve().exists():
                line = text.count("\n", 0, match.start()) + 1
                errors.append(f"{path.relative_to(ROOT)}:{line}: broken link {target}")
    return errors


def check_secrets_and_stale_commands(files: list[Path]) -> list[str]:
    errors: list[str] = []
    stale = {
        "cody-web --dev": "use `cody-web run --dev`",
        "cody-web --port": "use `cody-web run --port`",
        '"default_model"': "Config uses `model`",
    }
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in SECRET_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            errors.append(f"{path.relative_to(ROOT)}:{line}: possible persisted API key")
        if path.parts[-2:] == ("pages", "prompts"):
            continue
        for pattern, hint in stale.items():
            if pattern in text:
                errors.append(f"{path.relative_to(ROOT)}: stale `{pattern}`; {hint}")
    return errors


def check_python_fences(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in PYTHON_FENCE_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 2
            try:
                compile(
                    textwrap.dedent(match.group(1)),
                    f"{path.relative_to(ROOT)}:{line}",
                    "exec",
                    flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT,
                )
            except SyntaxError as exc:
                errors.append(
                    f"{path.relative_to(ROOT)}:{line}: invalid Python fence: {exc.msg}"
                )
    return errors


def check_config_reference() -> list[str]:
    from cody.core.config import Config

    text = (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8")
    errors: list[str] = []
    for name, field in Config.model_fields.items():
        if f"`{name}`" not in text and f'"{name}"' not in text:
            errors.append(f"docs/CONFIG.md: missing Config field `{name}`")
        model = field.annotation
        nested = getattr(model, "model_fields", {})
        for child in nested:
            dotted = f"{name}.{child}"
            if (
                f"`{dotted}`" not in text
                and f"`{child}`" not in text
                and f'"{child}"' not in text
            ):
                errors.append(f"docs/CONFIG.md: missing Config field `{dotted}`")
    return errors


def check_cli_reference() -> list[str]:
    from cody.cli.main import main

    text = (ROOT / "docs" / "CLI.md").read_text(encoding="utf-8")
    errors: list[str] = []
    for command_name in main.commands:
        if (
            f"`cody {command_name}`" not in text
            and f"cody {command_name}" not in text
        ):
            errors.append(
                f"docs/CLI.md: missing top-level command `cody {command_name}`"
            )
    for group in ("runs", "approvals", "artifacts", "timeline"):
        subcommands = getattr(main.commands[group], "commands", {})
        for subcommand in subcommands:
            literal = f"cody {group} {subcommand}"
            if literal not in text:
                errors.append(f"docs/CLI.md: missing command `{literal}`")
    return errors


def check_http_reference() -> list[str]:
    from web.backend.app import app

    text = (ROOT / "docs" / "API.md").read_text(encoding="utf-8")
    errors: list[str] = []

    def normalized(value: str) -> str:
        return re.sub(r"\{[^}]+\}", "{}", value)

    normalized_docs = normalized(text)
    for path in app.openapi()["paths"]:
        if normalized(path) not in normalized_docs:
            errors.append(f"docs/API.md: missing HTTP path `{path}`")
    return errors


def main() -> int:
    files = markdown_files()
    errors = [
        *check_local_links(files),
        *check_secrets_and_stale_commands(files),
        *check_python_fences(files),
        *check_config_reference(),
        *check_cli_reference(),
        *check_http_reference(),
    ]
    if errors:
        print("Documentation checks failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Documentation checks passed ({len(files)} Markdown files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
