"""CLI utility functions and shared state."""

from pathlib import Path
from typing import Optional

try:
    import click
    from rich.console import Console
    from rich.panel import Panel
except ImportError:
    raise SystemExit(
        "CLI requires extra dependencies. Install with:\n"
        "  pip install cody-ai[cli]"
    )

from ..core import Config, AgentRunner
from ..core.setup import SetupAnswers, build_config_from_answers
from ..shared import format_session_line

console = Console()


def _mask_api_key(key: Optional[str]) -> str:
    """Mask an API key for display: sk-abc...xyz"""
    if not key:
        return "(not set)"
    if len(key) <= 8:
        return key[:2] + "..." + key[-2:]
    return key[:6] + "..." + key[-3:]


def _interactive_setup() -> Config:
    """Interactive first-time configuration wizard.

    Prompts the user for API key, optional base URL, and model name,
    then saves the result to ~/.cody/config.json.
    Returns the newly created Config.
    """
    console.print(Panel(
        "[bold]Welcome to Cody![/bold]\n\n"
        "Let's configure your model API.",
        border_style="blue",
    ))

    # 1. API Key (required)
    api_key = click.prompt("\nAPI Key", prompt_suffix=": ")

    # 2. Base URL (optional — leave empty for Anthropic)
    base_url = click.prompt(
        "API Base URL (leave empty for Anthropic)",
        default="",
        prompt_suffix=": ",
    ).strip() or None

    # 3. Model name
    default_model = "anthropic:claude-sonnet-4-0" if not base_url else ""
    model = click.prompt("Model name", default=default_model, prompt_suffix=": ")

    # 4. Thinking mode
    enable_thinking = click.confirm("Enable thinking mode?", default=False)
    thinking_budget = None
    if enable_thinking:
        thinking_budget = click.prompt(
            "Thinking budget (tokens)", type=int, default=10000
        )

    # 5. Save
    answers = SetupAnswers(
        model=model,
        model_api_key=api_key,
        model_base_url=base_url,
        enable_thinking=enable_thinking,
        thinking_budget=thinking_budget,
    )
    config_data = build_config_from_answers(answers)
    cfg = Config(**config_data)
    config_path = Path.home() / ".cody" / "config.json"
    cfg.save(config_path)

    console.print(f"\n[green]Configuration saved to {config_path}[/green]")
    return cfg


def _ensure_config_ready(config: Config) -> Config:
    """Check if config is ready; if not, run interactive setup."""
    if config.is_ready():
        return config
    missing = config.missing_fields()
    console.print(f"[yellow]Configuration incomplete: {', '.join(missing)}[/yellow]")
    return _interactive_setup()


def _get_input() -> str:
    """Get user input, supporting multi-line with trailing backslash"""
    try:
        from prompt_toolkit import prompt as pt_prompt
        from prompt_toolkit.history import InMemoryHistory

        if not hasattr(_get_input, '_history'):
            _get_input._history = InMemoryHistory()

        return pt_prompt(
            "You > ",
            history=_get_input._history,
            multiline=False,
        )
    except ImportError:
        # Fallback to basic input
        return input("You > ")


def _build_history_from_session(session) -> list:
    """Convert stored session messages to pydantic-ai message format"""
    return AgentRunner.messages_to_history(session.messages)


def _handle_command(cmd: str, session, store, console: Console) -> bool:
    """Handle a slash command. Returns False if we should exit the REPL."""
    cmd = cmd.strip().lower()

    if cmd in ("/quit", "/exit", "/q"):
        console.print("[dim]Bye![/dim]")
        return False

    if cmd == "/sessions":
        sessions = store.list_sessions(limit=10)
        if not sessions:
            console.print("[yellow]No sessions found[/yellow]")
        else:
            console.print("[bold]Recent sessions:[/bold]")
            for s in sessions:
                count = store.get_message_count(s.id)
                line = format_session_line(
                    s.id, s.title, count, s.updated_at, session.id
                )
                console.print(f"[dim]{line}[/dim]")
        console.print()
        return True

    if cmd == "/clear":
        console.clear()
        console.print("[dim]Screen cleared. Session continues.[/dim]\n")
        return True

    if cmd == "/help":
        console.print(
            Panel(
                "/quit     - Exit chat\n"
                "/sessions - List recent sessions\n"
                "/clear    - Clear screen\n"
                "/help     - Show this help",
                title="[bold]Commands[/bold]",
                border_style="blue",
            )
        )
        console.print()
        return True

    console.print(f"[yellow]Unknown command: {cmd}[/yellow]")
    console.print("[dim]Type /help for available commands[/dim]\n")
    return True
