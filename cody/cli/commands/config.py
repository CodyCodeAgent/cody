"""CLI configuration commands."""

from pathlib import Path

import click

from ...core import Config
from ...shared import resolve_config_path
from ..utils import console, _mask_api_key, _interactive_setup


@click.group()
def config():
    """Manage configuration"""


@config.command('show')
def config_show():
    """Show current configuration"""
    cfg = Config.load(workdir=Path.cwd())
    data = cfg.model_dump(exclude_none=True)
    # Mask sensitive fields for display
    if "model_api_key" in data:
        data["model_api_key"] = _mask_api_key(data["model_api_key"])
    if "auth" in data:
        for key in ("api_key", "token", "refresh_token"):
            if key in data["auth"]:
                data["auth"][key] = _mask_api_key(data["auth"][key])
    import json as _json
    console.print_json(_json.dumps(data, indent=2, default=str))


@config.command('set')
@click.argument('key')
@click.argument('value')
def config_set(key, value):
    """Set configuration value

    Supported keys: model, model_base_url, model_api_key, enable_thinking, thinking_budget
    """
    cfg = Config.load(workdir=Path.cwd())

    if key == 'model':
        cfg.model = value
    elif key == 'model_base_url':
        cfg.model_base_url = value
    elif key == 'model_api_key':
        cfg.model_api_key = value
    elif key == 'enable_thinking':
        cfg.enable_thinking = value.lower() in ("1", "true", "yes")
    elif key == 'thinking_budget':
        cfg.thinking_budget = int(value)
    else:
        console.print(f"[yellow]Unknown config key: {key}[/yellow]")
        console.print("[dim]Supported: model, model_base_url, model_api_key, enable_thinking, thinking_budget[/dim]")
        return

    cfg.save(resolve_config_path())
    display_value = _mask_api_key(value) if "key" in key else value
    console.print(f"[green]Set {key} = {display_value}[/green]")


@config.command('setup')
def config_setup():
    """Interactive configuration wizard

    Set up your AI model provider, API key, and preferences.
    Configuration is saved to ~/.cody/config.json.
    """
    _interactive_setup()
