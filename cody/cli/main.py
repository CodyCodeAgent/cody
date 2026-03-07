"""CLI main entry point — Click group and core commands."""

import asyncio
import sys
from pathlib import Path

import click
from rich.markup import escape as rich_escape
from rich.panel import Panel

from ..core import Config, AgentRunner, SessionStore
from ..core.log import setup_logging
from .utils import (
    console, _ensure_config_ready, _get_input,
    _handle_command, _build_history_from_session,
)
from .rendering import _render_stream
from ..shared import auto_title
from .commands.sessions import sessions
from .commands.skills import skills
from .commands.config import config
from .commands.init_cmd import init


@click.group()
@click.version_option(version=__import__("cody").__version__)
def main():
    """Cody - AI Coding Assistant

    A powerful AI assistant with RPC support, dynamic skills, and MCP integration.
    """


# Register sub-groups and commands
main.add_command(sessions)
main.add_command(skills)
main.add_command(config)
main.add_command(init)


# ── Run command ──────────────────────────────────────────────────────────────


@main.command()
@click.argument('prompt', required=False)
@click.option('--model', help='AI model to use (temporary override)')
@click.option('--thinking/--no-thinking', default=None, help='Enable/disable thinking mode')
@click.option('--thinking-budget', type=int, default=None, help='Max tokens for thinking (e.g. 10000)')
@click.option('--workdir', type=click.Path(exists=True), help='Working directory')
@click.option('--allow-root', 'extra_roots', multiple=True, type=click.Path(exists=True),
              help='Additional directory to allow file access (repeatable)')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def run(prompt, model, thinking, thinking_budget, workdir, extra_roots, verbose):
    """Run a single task with Cody

    Examples:
        cody run "create a hello.py file"
        cody run "refactor main.py to use async"
        cody run --model qwen3.5 "写个排序算法"
        cody run --workdir /proj/frontend --allow-root /proj/backend "sync configs"
    """
    setup_logging(verbose=verbose)

    if not prompt:
        console.print("[yellow]Please provide a prompt[/yellow]")
        console.print("Example: cody run 'create a hello.py file'")
        return

    workdir_path = Path(workdir) if workdir else Path.cwd()
    cfg = Config.load(workdir=workdir_path)
    cfg = _ensure_config_ready(cfg)
    cfg.apply_overrides(
        model=model,
        enable_thinking=thinking,
        thinking_budget=thinking_budget,
        extra_roots=list(extra_roots) or None,
    )

    runner = AgentRunner(config=cfg, workdir=workdir_path, extra_roots=[Path(r) for r in extra_roots])

    if verbose:
        console.print(f"[dim]Model: {cfg.model}[/dim]")
        console.print(f"[dim]Workdir: {runner.workdir}[/dim]")
        if cfg.enable_thinking:
            budget = f" (budget: {cfg.thinking_budget})" if cfg.thinking_budget else ""
            console.print(f"[dim]Thinking: enabled{budget}[/dim]")

    async def _run_stream():
        await runner.start_mcp()
        try:
            result = await _render_stream(runner.run_stream(prompt), verbose=verbose)
            if verbose and result:
                usage = result.usage()
                if usage:
                    console.print(f"[dim]Tokens: {usage.total_tokens}[/dim]")
        finally:
            await runner.stop_mcp()
            await runner.stop_lsp()

    asyncio.run(_run_stream())


# ── Chat command (interactive REPL) ──────────────────────────────────────────


@main.command()
@click.option('--model', help='AI model to use (temporary override)')
@click.option('--thinking/--no-thinking', default=None, help='Enable/disable thinking mode')
@click.option('--thinking-budget', type=int, default=None, help='Max tokens for thinking (e.g. 10000)')
@click.option('--workdir', type=click.Path(exists=True), help='Working directory')
@click.option('--allow-root', 'extra_roots', multiple=True, type=click.Path(exists=True),
              help='Additional directory to allow file access (repeatable)')
@click.option('--session', 'session_id', default=None, help='Resume a session by ID')
@click.option('--continue', 'continue_last', is_flag=True, help='Continue last session')
def chat(model, thinking, thinking_budget, workdir, extra_roots, session_id, continue_last):
    """Interactive chat with Cody

    Start an interactive session where you can have a multi-turn conversation.

    Examples:
        cody chat
        cody chat --model anthropic:claude-sonnet-4-0
        cody chat --continue
        cody chat --session abc123
        cody chat --workdir /proj/frontend --allow-root /proj/backend
    """
    setup_logging()

    workdir_path = Path(workdir) if workdir else Path.cwd()

    cfg = Config.load(workdir=workdir_path)
    cfg = _ensure_config_ready(cfg)
    cfg.apply_overrides(
        model=model,
        enable_thinking=thinking,
        thinking_budget=thinking_budget,
        extra_roots=list(extra_roots) or None,
    )
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
            model=cfg.model,
            workdir=str(workdir_path),
        )

    runner = AgentRunner(config=cfg, workdir=workdir_path, extra_roots=[Path(r) for r in extra_roots])

    # Print header
    console.print(
        Panel(
            f"Model: {cfg.model}\n"
            f"Workdir: {workdir_path}\n"
            f"Session: {session.id}",
            title="[bold]Cody Chat[/bold]",
            border_style="blue",
        )
    )
    console.print("[dim]Type your message. Commands: /quit, /sessions, /clear, /help[/dim]\n")

    # Build message history from session
    message_history = _build_history_from_session(session)

    async def _chat_loop():
        nonlocal message_history
        await runner.start_mcp()
        try:
            while True:
                try:
                    loop = asyncio.get_event_loop()
                    user_input = await loop.run_in_executor(None, _get_input)
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
                    store.update_title(session.id, auto_title(user_input))

                # Save user message
                store.add_message(session.id, "user", user_input)

                # Run agent with streaming
                try:
                    result = await _render_stream(
                        runner.run_stream(user_input, message_history=message_history),
                    )

                    # Update history for next turn
                    if result:
                        message_history = result.all_messages()
                        store.add_message(session.id, "assistant", result.output)

                except Exception as e:
                    console.print(f"\n[red]Error: {rich_escape(str(e))}[/red]\n")

        finally:
            await runner.stop_mcp()
            await runner.stop_lsp()

    try:
        asyncio.run(_chat_loop())
    except Exception as e:
        console.print(f"[red]Fatal error: {rich_escape(str(e))}[/red]")
        sys.exit(1)


# ── TUI command ─────────────────────────────────────────────────────────────


@main.command()
@click.option('--model', help='AI model to use (temporary override)')
@click.option('--thinking/--no-thinking', default=None, help='Enable/disable thinking mode')
@click.option('--thinking-budget', type=int, default=None, help='Max tokens for thinking (e.g. 10000)')
@click.option('--workdir', type=click.Path(exists=True), help='Working directory')
@click.option('--allow-root', 'extra_roots', multiple=True, type=click.Path(exists=True),
              help='Additional directory to allow file access (repeatable)')
@click.option('--session', 'session_id', default=None, help='Resume a session by ID')
@click.option('--continue', 'continue_last', is_flag=True, help='Continue last session')
def tui(model, thinking, thinking_budget, workdir, extra_roots, session_id, continue_last):
    """Launch interactive Terminal UI

    Full-screen terminal interface with streaming, session management, and keyboard shortcuts.

    Examples:
        cody tui
        cody tui --model anthropic:claude-sonnet-4-0
        cody tui --continue
        cody tui --workdir /proj/frontend --allow-root /proj/backend
    """
    setup_logging()

    # Check config readiness before launching TUI (still in normal terminal)
    workdir_path = Path(workdir) if workdir else Path.cwd()
    cfg = Config.load(workdir=workdir_path)
    _ensure_config_ready(cfg)

    from ..tui import run_tui
    run_tui(
        model=model,
        thinking=thinking,
        thinking_budget=thinking_budget,
        workdir=workdir,
        extra_roots=list(extra_roots) or None,
        session_id=session_id,
        continue_last=continue_last,
    )


if __name__ == '__main__':
    main()
