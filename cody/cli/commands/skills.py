"""CLI skills management commands."""

from pathlib import Path

import click
from rich.markdown import Markdown
from rich.panel import Panel

from ...sdk.client import CodyClient
from ..utils import console


def _make_client() -> CodyClient:
    return CodyClient(workdir=str(Path.cwd()))


@click.group()
def skills():
    """Manage skills"""


@skills.command('list')
def skills_list():
    """List all available skills"""
    client = _make_client()
    all_skills = client.list_skills()

    if not all_skills:
        console.print("[yellow]No skills found[/yellow]")
        return

    console.print("[bold]Available Skills:[/bold]\n")

    for skill in sorted(all_skills, key=lambda s: s["name"]):
        status = "[green]on[/green]" if skill["enabled"] else "[red]off[/red]"
        source = f"[dim]({skill['source']})[/dim]"
        console.print(f"  [{status}] {skill['name']} {source}")
        console.print(f"        {skill['description']}")


@skills.command('show')
@click.argument('skill_name')
def skills_show(skill_name):
    """Show skill documentation"""
    client = _make_client()
    try:
        skill = client.get_skill(skill_name)
    except Exception:
        console.print(f"[red]Skill not found: {skill_name}[/red]")
        return

    md = Markdown(skill["documentation"])
    console.print(Panel(md, title=f"[bold]{skill['name']}[/bold]", border_style="blue"))


@skills.command('enable')
@click.argument('skill_name')
def skills_enable(skill_name):
    """Enable a skill"""
    client = _make_client()
    try:
        client.enable_skill(skill_name)
        console.print(f"[green]Enabled skill: {skill_name}[/green]")
    except Exception:
        console.print(f"[red]Skill not found: {skill_name}[/red]")


@skills.command('disable')
@click.argument('skill_name')
def skills_disable(skill_name):
    """Disable a skill"""
    client = _make_client()
    try:
        client.disable_skill(skill_name)
        console.print(f"[green]Disabled skill: {skill_name}[/green]")
    except Exception:
        console.print(f"[red]Skill not found: {skill_name}[/red]")
