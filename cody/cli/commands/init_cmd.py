"""CLI init command."""

import asyncio
from pathlib import Path

import click

from ...core import Config
from ...core.project_instructions import CODY_MD_FILENAME, generate_project_instructions
from ..utils import console, _interactive_setup


@click.command()
def init():
    """Initialize Cody in current directory"""
    workdir = Path.cwd()
    cody_dir = workdir / ".cody"
    skills_dir = cody_dir / "skills"
    config_file = cody_dir / "config.json"
    cody_md_file = workdir / CODY_MD_FILENAME

    created: list[str] = []

    # Create .cody/ scaffold only when it doesn't already exist.
    if cody_dir.exists():
        console.print("[yellow].cody directory already exists — skipping scaffold[/yellow]")
    else:
        cody_dir.mkdir()
        skills_dir.mkdir()
        config = Config.load(workdir=workdir)
        config.save(config_file)
        created += [".cody/", ".cody/skills/", ".cody/config.json"]

    # Always (re-)generate CODY.md via AI analysis.
    config = Config.load(workdir=workdir)
    verb = "Updated" if cody_md_file.exists() else "Created"
    with console.status("[cyan]Analyzing project to generate CODY.md…[/cyan]"):
        cody_md_content = asyncio.run(generate_project_instructions(workdir, config))
    cody_md_file.write_text(cody_md_content, encoding="utf-8")
    created.append(f"{CODY_MD_FILENAME} [dim](AI-generated)[/dim]")

    console.print("[green]Initialized Cody in current directory[/green]")
    for item in created[:-1]:
        console.print(f"  Created {item}")
    console.print(f"  {verb} {created[-1]}")

    # Check config readiness and offer setup if needed
    config = Config.load(workdir=workdir)
    if not config.is_ready():
        console.print("\n[yellow]No API key configured yet.[/yellow]")
        if click.confirm("Run setup now?", default=True):
            _interactive_setup()
