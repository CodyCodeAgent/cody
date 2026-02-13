"""CLI interface for Cody"""

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .core import Config, AgentRunner, SessionStore

console = Console()


@click.group()
@click.version_option()
def main():
    """Cody - AI Coding Assistant

    A powerful AI assistant with RPC support, dynamic skills, and MCP integration.
    """
    pass


# ── Run command ──────────────────────────────────────────────────────────────


@main.command()
@click.argument('prompt', required=False)
@click.option('--model', help='AI model to use')
@click.option('--workdir', type=click.Path(exists=True), help='Working directory')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def run(prompt, model, workdir, verbose):
    """Run a single task with Cody

    Examples:
        cody run "create a hello.py file"
        cody run "refactor main.py to use async"
    """
    if not prompt:
        console.print("[yellow]Please provide a prompt[/yellow]")
        console.print("Example: cody run 'create a hello.py file'")
        return

    config = Config.load()
    if model:
        config.model = model

    runner = AgentRunner(config=config, workdir=workdir)

    if verbose:
        console.print(f"[dim]Model: {config.model}[/dim]")
        console.print(f"[dim]Workdir: {runner.workdir}[/dim]")

    with console.status("[bold green]Thinking..."):
        result = runner.run_sync(prompt)

    console.print(Panel(result.output, title="[bold green]Cody", border_style="green"))

    if verbose:
        console.print(f"\n[dim]Tokens: {result.usage().total_tokens}[/dim]")


# ── Chat command (interactive REPL) ──────────────────────────────────────────


@main.command()
@click.option('--model', help='AI model to use')
@click.option('--workdir', type=click.Path(exists=True), help='Working directory')
@click.option('--session', 'session_id', default=None, help='Resume a session by ID')
@click.option('--continue', 'continue_last', is_flag=True, help='Continue last session')
def chat(model, workdir, session_id, continue_last):
    """Interactive chat with Cody

    Start an interactive session where you can have a multi-turn conversation.

    Examples:
        cody chat
        cody chat --model anthropic:claude-sonnet-4-0
        cody chat --continue
        cody chat --session abc123
    """
    config = Config.load()
    if model:
        config.model = model

    workdir_path = Path(workdir) if workdir else Path.cwd()
    store = SessionStore()

    # Resolve session
    session = None
    if session_id:
        session = store.get_session(session_id)
        if not session:
            console.print(f"[red]Session not found: {session_id}[/red]")
            return
        console.print(f"[dim]Resuming session: {session.title} ({session.id})[/dim]")
    elif continue_last:
        session = store.get_latest_session(workdir=str(workdir_path))
        if not session:
            console.print("[yellow]No previous session found for this directory[/yellow]")
            session = None
        else:
            console.print(f"[dim]Continuing session: {session.title} ({session.id})[/dim]")

    # Create new session if needed
    if session is None:
        session = store.create_session(
            title="Chat session",
            model=config.model,
            workdir=str(workdir_path),
        )

    runner = AgentRunner(config=config, workdir=workdir_path)

    # Print header
    console.print(
        Panel(
            f"Model: {config.model}\n"
            f"Workdir: {workdir_path}\n"
            f"Session: {session.id}",
            title="[bold]Cody Chat[/bold]",
            border_style="blue",
        )
    )
    console.print("[dim]Type your message. Commands: /quit, /sessions, /clear, /help[/dim]\n")

    # Build message history from session
    message_history = _build_history_from_session(session)

    # REPL loop
    try:
        while True:
            try:
                user_input = _get_input()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Bye![/dim]")
                break

            if not user_input.strip():
                continue

            # Handle commands
            if user_input.startswith("/"):
                should_continue = _handle_command(
                    user_input, session, store, console
                )
                if not should_continue:
                    break
                continue

            # Auto-title from first message
            if store.get_message_count(session.id) == 0:
                title = user_input[:60].strip()
                if len(user_input) > 60:
                    title += "..."
                store.update_title(session.id, title)

            # Save user message
            store.add_message(session.id, "user", user_input)

            # Run agent
            try:
                with console.status("[bold green]Thinking..."):
                    result = runner.run_sync(user_input, message_history=message_history)

                # Update history for next turn
                message_history = result.all_messages()

                # Display response
                assistant_text = result.output
                console.print()
                console.print(
                    Panel(
                        Markdown(assistant_text),
                        title="[bold green]Cody[/bold green]",
                        border_style="green",
                    )
                )
                console.print()

                # Save assistant message
                store.add_message(session.id, "assistant", assistant_text)

            except Exception as e:
                console.print(f"\n[red]Error: {e}[/red]\n")

    except Exception as e:
        console.print(f"[red]Fatal error: {e}[/red]")
        sys.exit(1)


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
    from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart

    history: list = []
    for msg in session.messages:
        if msg.role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=msg.content)]))
        elif msg.role == "assistant":
            history.append(ModelResponse(parts=[TextPart(content=msg.content)]))
    return history


def _handle_command(cmd: str, session, store, console: Console) -> bool:
    """Handle a slash command. Returns False if we should exit the REPL."""
    cmd = cmd.strip().lower()

    if cmd in ("/quit", "/exit", "/q"):
        console.print("[dim]Bye![/dim]")
        return False

    elif cmd == "/sessions":
        sessions = store.list_sessions(limit=10)
        if not sessions:
            console.print("[yellow]No sessions found[/yellow]")
        else:
            console.print("[bold]Recent sessions:[/bold]")
            for s in sessions:
                count = store.get_message_count(s.id)
                marker = " [green]<< current[/green]" if s.id == session.id else ""
                console.print(
                    f"  {s.id}  {s.title[:40]:<40}  "
                    f"[dim]{count} msgs  {s.updated_at[:10]}[/dim]{marker}"
                )
        console.print()
        return True

    elif cmd == "/clear":
        console.clear()
        console.print("[dim]Screen cleared. Session continues.[/dim]\n")
        return True

    elif cmd == "/help":
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

    else:
        console.print(f"[yellow]Unknown command: {cmd}[/yellow]")
        console.print("[dim]Type /help for available commands[/dim]\n")
        return True


# ── Session management commands ──────────────────────────────────────────────


@main.group()
def sessions():
    """Manage chat sessions"""
    pass


@sessions.command('list')
@click.option('--limit', default=20, help='Number of sessions to show')
def sessions_list(limit):
    """List recent chat sessions"""
    store = SessionStore()
    all_sessions = store.list_sessions(limit=limit)

    if not all_sessions:
        console.print("[yellow]No sessions found[/yellow]")
        return

    console.print("[bold]Recent sessions:[/bold]\n")
    for s in all_sessions:
        count = store.get_message_count(s.id)
        console.print(
            f"  [bold]{s.id}[/bold]  {s.title[:50]:<50}  "
            f"[dim]{count} msgs  {s.updated_at[:10]}[/dim]"
        )


@sessions.command('show')
@click.argument('session_id')
def sessions_show(session_id):
    """Show a session's conversation"""
    store = SessionStore()
    session = store.get_session(session_id)

    if not session:
        console.print(f"[red]Session not found: {session_id}[/red]")
        return

    console.print(
        Panel(
            f"Title: {session.title}\n"
            f"Model: {session.model}\n"
            f"Workdir: {session.workdir}\n"
            f"Created: {session.created_at[:19]}\n"
            f"Messages: {len(session.messages)}",
            title=f"[bold]Session {session.id}[/bold]",
            border_style="blue",
        )
    )

    for msg in session.messages:
        if msg.role == "user":
            console.print(f"\n[bold blue]You:[/bold blue] {msg.content}")
        else:
            console.print("\n[bold green]Cody:[/bold green]")
            console.print(Markdown(msg.content))


@sessions.command('delete')
@click.argument('session_id')
@click.confirmation_option(prompt='Are you sure you want to delete this session?')
def sessions_delete(session_id):
    """Delete a chat session"""
    store = SessionStore()
    if store.delete_session(session_id):
        console.print(f"[green]Deleted session: {session_id}[/green]")
    else:
        console.print(f"[red]Session not found: {session_id}[/red]")


# ── Init command ─────────────────────────────────────────────────────────────


@main.command()
def init():
    """Initialize Cody in current directory"""
    cody_dir = Path.cwd() / ".cody"
    skills_dir = cody_dir / "skills"
    config_file = cody_dir / "config.json"

    if cody_dir.exists():
        console.print("[yellow].cody directory already exists[/yellow]")
        return

    cody_dir.mkdir()
    skills_dir.mkdir()

    config = Config()
    config.save(config_file)

    console.print("[green]Initialized Cody in current directory[/green]")
    console.print("  Created .cody/")
    console.print("  Created .cody/skills/")
    console.print("  Created .cody/config.json")


# ── Skills commands ──────────────────────────────────────────────────────────


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
        status = "[green]on[/green]" if skill.enabled else "[red]off[/red]"
        source = f"[dim]({skill.source})[/dim]"
        console.print(f"  [{status}] {skill.name} {source}")
        console.print(f"        {skill.description}")


@skills.command('show')
@click.argument('skill_name')
def skills_show(skill_name):
    """Show skill documentation"""
    config = Config.load()
    runner = AgentRunner(config=config)

    skill = runner.skill_manager.get_skill(skill_name)
    if not skill:
        console.print(f"[red]Skill not found: {skill_name}[/red]")
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
        console.print(f"[red]Skill not found: {skill_name}[/red]")
        return

    runner.skill_manager.enable_skill(skill_name)

    config_path = Path.cwd() / ".cody" / "config.json"
    if not config_path.exists():
        config_path = Path.home() / ".cody" / "config.json"
    config.save(config_path)

    console.print(f"[green]Enabled skill: {skill_name}[/green]")


@skills.command('disable')
@click.argument('skill_name')
def skills_disable(skill_name):
    """Disable a skill"""
    config = Config.load()
    runner = AgentRunner(config=config)

    skill = runner.skill_manager.get_skill(skill_name)
    if not skill:
        console.print(f"[red]Skill not found: {skill_name}[/red]")
        return

    runner.skill_manager.disable_skill(skill_name)

    config_path = Path.cwd() / ".cody" / "config.json"
    if not config_path.exists():
        config_path = Path.home() / ".cody" / "config.json"
    config.save(config_path)

    console.print(f"[green]Disabled skill: {skill_name}[/green]")


# ── Config commands ──────────────────────────────────────────────────────────


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

    if key == 'model':
        cfg.model = value
    else:
        console.print(f"[yellow]Unknown config key: {key}[/yellow]")
        return

    config_path = Path.cwd() / ".cody" / "config.json"
    if not config_path.exists():
        config_path = Path.home() / ".cody" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

    cfg.save(config_path)
    console.print(f"[green]Set {key} = {value}[/green]")


if __name__ == '__main__':
    main()
