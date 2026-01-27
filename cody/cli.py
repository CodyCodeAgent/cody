"""CLI interface for Cody"""

import click
from pathlib import Path
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from .core import Config, AgentRunner

console = Console()


@click.group()
@click.version_option()
def main():
    """🤖 Cody - AI Coding Assistant
    
    A powerful AI assistant with RPC support, dynamic skills, and MCP integration.
    """
    pass


@main.command()
@click.argument('prompt', required=False)
@click.option('--model', help='AI model to use')
@click.option('--workdir', type=click.Path(exists=True), help='Working directory')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def run(prompt, model, workdir, verbose):
    """Run a task with Cody
    
    Examples:
        cody run "create a hello.py file"
        cody run "refactor main.py to use async"
    """
    if not prompt:
        console.print("[yellow]Please provide a prompt[/yellow]")
        console.print("Example: cody run 'create a hello.py file'")
        return
    
    # Load config
    config = Config.load()
    if model:
        config.model = model
    
    # Run agent
    runner = AgentRunner(config=config, workdir=workdir)
    
    if verbose:
        console.print(f"[dim]Model: {config.model}[/dim]")
        console.print(f"[dim]Workdir: {runner.workdir}[/dim]")
    
    with console.status("[bold green]Thinking..."):
        result = runner.run_sync(prompt)
    
    # Display result
    console.print(Panel(result.output, title="[bold green]✓ Cody", border_style="green"))
    
    if verbose:
        console.print(f"\n[dim]Tokens: {result.usage().total_tokens}[/dim]")


@main.command()
def init():
    """Initialize Cody in current directory"""
    cody_dir = Path.cwd() / ".cody"
    skills_dir = cody_dir / "skills"
    config_file = cody_dir / "config.json"
    
    if cody_dir.exists():
        console.print("[yellow]⚠ .cody directory already exists[/yellow]")
        return
    
    # Create directories
    cody_dir.mkdir()
    skills_dir.mkdir()
    
    # Create default config
    config = Config()
    config.save(config_file)
    
    console.print("[green]✓ Initialized Cody in current directory[/green]")
    console.print(f"  • Created .cody/")
    console.print(f"  • Created .cody/skills/")
    console.print(f"  • Created .cody/config.json")


@main.group()
def skills():
    """Manage skills"""
    pass


@skills.command('list')
def skills_list():
    """List all available skills"""
    config = Config.load()
    runner = AgentRunner(config=config)
    
    all_skills = runner.skill_manager.list_skills()
    
    if not all_skills:
        console.print("[yellow]No skills found[/yellow]")
        return
    
    console.print("[bold]Available Skills:[/bold]\n")
    
    for skill in sorted(all_skills, key=lambda s: s.name):
        status = "✅" if skill.enabled else "⏸️ "
        source = f"[dim]({skill.source})[/dim]"
        console.print(f"  {status} {skill.name} {source}")
        console.print(f"      {skill.description}")


@skills.command('show')
@click.argument('skill_name')
def skills_show(skill_name):
    """Show skill documentation"""
    config = Config.load()
    runner = AgentRunner(config=config)
    
    skill = runner.skill_manager.get_skill(skill_name)
    if not skill:
        console.print(f"[red]✗ Skill not found: {skill_name}[/red]")
        return
    
    md = Markdown(skill.documentation)
    console.print(Panel(md, title=f"[bold]{skill.name}[/bold]", border_style="blue"))


@skills.command('enable')
@click.argument('skill_name')
def skills_enable(skill_name):
    """Enable a skill"""
    config = Config.load()
    runner = AgentRunner(config=config)
    
    skill = runner.skill_manager.get_skill(skill_name)
    if not skill:
        console.print(f"[red]✗ Skill not found: {skill_name}[/red]")
        return
    
    runner.skill_manager.enable_skill(skill_name)
    
    # Save config
    config_path = Path.cwd() / ".cody" / "config.json"
    if not config_path.exists():
        config_path = Path.home() / ".cody" / "config.json"
    config.save(config_path)
    
    console.print(f"[green]✓ Enabled skill: {skill_name}[/green]")


@skills.command('disable')
@click.argument('skill_name')
def skills_disable(skill_name):
    """Disable a skill"""
    config = Config.load()
    runner = AgentRunner(config=config)
    
    skill = runner.skill_manager.get_skill(skill_name)
    if not skill:
        console.print(f"[red]✗ Skill not found: {skill_name}[/red]")
        return
    
    runner.skill_manager.disable_skill(skill_name)
    
    # Save config
    config_path = Path.cwd() / ".cody" / "config.json"
    if not config_path.exists():
        config_path = Path.home() / ".cody" / "config.json"
    config.save(config_path)
    
    console.print(f"[green]✓ Disabled skill: {skill_name}[/green]")


@main.group()
def config():
    """Manage configuration"""
    pass


@config.command('show')
def config_show():
    """Show current configuration"""
    cfg = Config.load()
    console.print_json(cfg.model_dump_json(indent=2))


@config.command('set')
@click.argument('key')
@click.argument('value')
def config_set(key, value):
    """Set configuration value"""
    cfg = Config.load()
    
    # Simple key=value setting
    if key == 'model':
        cfg.model = value
    else:
        console.print(f"[yellow]Unknown config key: {key}[/yellow]")
        return
    
    # Save
    config_path = Path.cwd() / ".cody" / "config.json"
    if not config_path.exists():
        config_path = Path.home() / ".cody" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
    
    cfg.save(config_path)
    console.print(f"[green]✓ Set {key} = {value}[/green]")


if __name__ == '__main__':
    main()
