"""CLI skills management commands."""

from pathlib import Path

import click
from rich.markdown import Markdown
from rich.panel import Panel

from ...core import Config
from ...core.skill_manager import SkillManager
from ...shared import resolve_config_path
from ..utils import console


@click.group()
def skills():
    """Manage skills"""


@skills.command('list')
def skills_list():
    """List all available skills"""
    workdir = Path.cwd()
    cfg = Config.load(workdir=workdir)
    sm = SkillManager(config=cfg, workdir=workdir)

    all_skills = sm.list_skills()

    if not all_skills:
        console.print("[yellow]No skills found[/yellow]")
        return

    console.print("[bold]Available Skills:[/bold]\n")

    for skill in sorted(all_skills, key=lambda s: s.name):
        status = "[green]on[/green]" if skill.enabled else "[red]off[/red]"
        source = f"[dim]({skill.source})[/dim]"
        console.print(f"  [{status}] {skill.name} {source}")
        console.print(f"        {skill.description}")


@skills.command('show')
@click.argument('skill_name')
def skills_show(skill_name):
    """Show skill documentation"""
    workdir = Path.cwd()
    cfg = Config.load(workdir=workdir)
    sm = SkillManager(config=cfg, workdir=workdir)

    skill = sm.get_skill(skill_name)
    if not skill:
        console.print(f"[red]Skill not found: {skill_name}[/red]")
        return

    md = Markdown(skill.documentation)
    console.print(Panel(md, title=f"[bold]{skill.name}[/bold]", border_style="blue"))


@skills.command('enable')
@click.argument('skill_name')
def skills_enable(skill_name):
    """Enable a skill"""
    workdir = Path.cwd()
    cfg = Config.load(workdir=workdir)
    sm = SkillManager(config=cfg, workdir=workdir)

    skill = sm.get_skill(skill_name)
    if not skill:
        console.print(f"[red]Skill not found: {skill_name}[/red]")
        return

    sm.enable_skill(skill_name)
    cfg.save(resolve_config_path())

    console.print(f"[green]Enabled skill: {skill_name}[/green]")


@skills.command('disable')
@click.argument('skill_name')
def skills_disable(skill_name):
    """Disable a skill"""
    workdir = Path.cwd()
    cfg = Config.load(workdir=workdir)
    sm = SkillManager(config=cfg, workdir=workdir)

    skill = sm.get_skill(skill_name)
    if not skill:
        console.print(f"[red]Skill not found: {skill_name}[/red]")
        return

    sm.disable_skill(skill_name)
    cfg.save(resolve_config_path())

    console.print(f"[green]Disabled skill: {skill_name}[/green]")
