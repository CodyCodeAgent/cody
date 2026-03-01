"""CLI interface for Cody"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape as rich_escape
from rich.panel import Panel

from .core import Config, AgentRunner, SessionStore
from .core.runner import (
    CodyResult, CompactEvent, ThinkingEvent, TextDeltaEvent,
    ToolCallEvent, ToolResultEvent, DoneEvent,
)

console = Console()

_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


async def _tool_spinner(tool_name: str, start: float) -> None:
    """Show an animated spinner while a tool is executing."""
    i = 0
    try:
        while True:
            elapsed = time.monotonic() - start
            frame = _SPINNER_FRAMES[i % len(_SPINNER_FRAMES)]
            sys.stdout.write(
                f"\r    {frame} {tool_name} running... ({elapsed:.0f}s)"
            )
            sys.stdout.flush()
            i += 1
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        elapsed = time.monotonic() - start
        sys.stdout.write(f"\r    ✓ {tool_name} done ({elapsed:.1f}s)\n")
        sys.stdout.flush()


async def _render_stream(stream, *, verbose: bool = False) -> "Optional[CodyResult]":
    """Consume a StreamEvent async generator and render to console.

    Shared by both `run` and `chat` commands.
    Returns the CodyResult from the DoneEvent, or None.
    """
    in_thinking = False
    thinking_buf = []
    result = None
    spinner_task: Optional[asyncio.Task] = None

    async def _stop_spinner():
        nonlocal spinner_task
        if spinner_task and not spinner_task.done():
            spinner_task.cancel()
            try:
                await spinner_task
            except asyncio.CancelledError:
                pass
        spinner_task = None

    async for event in stream:
        if isinstance(event, CompactEvent):
            console.print(
                f"  [yellow]⚡ 上下文已压缩：{event.original_messages} → "
                f"{event.compacted_messages} 条消息，"
                f"节省约 ~{event.estimated_tokens_saved} tokens[/yellow]"
            )
        elif isinstance(event, ThinkingEvent):
            in_thinking = True
            thinking_buf.append(event.content)
        elif isinstance(event, ToolCallEvent):
            await _stop_spinner()
            if in_thinking:
                console.print(rich_escape("".join(thinking_buf)), style="dim")
                thinking_buf.clear()
                in_thinking = False
            args_str = ", ".join(f"{k}={v!r}" for k, v in list(event.args.items())[:3])
            console.print(f"  [dim]→ {rich_escape(event.tool_name)}({rich_escape(args_str)})[/dim]")
            spinner_task = asyncio.create_task(
                _tool_spinner(event.tool_name, time.monotonic())
            )
        elif isinstance(event, ToolResultEvent):
            await _stop_spinner()
            if verbose:
                preview = event.result[:200]
                console.print(f"    [dim]{rich_escape(preview)}[/dim]")
        elif isinstance(event, TextDeltaEvent):
            await _stop_spinner()
            if in_thinking:
                console.print(rich_escape("".join(thinking_buf)), style="dim")
                thinking_buf.clear()
                in_thinking = False
            console.print(event.content, end="")
        elif isinstance(event, DoneEvent):
            await _stop_spinner()
            if in_thinking:
                console.print(rich_escape("".join(thinking_buf)), style="dim")
                thinking_buf.clear()
            result = event.result
    console.print()
    return result


@click.group()
@click.version_option(package_name="cody-ai")
def main():
    """Cody - AI Coding Assistant

    A powerful AI assistant with RPC support, dynamic skills, and MCP integration.
    """
    pass


# ── Run command ──────────────────────────────────────────────────────────────


@main.command()
@click.argument('prompt', required=False)
@click.option('--model', help='AI model to use')
@click.option('--model-base-url', help='Custom OpenAI-compatible API base URL')
@click.option('--model-api-key', help='API key for custom model provider')
@click.option('--coding-plan-key', help='Aliyun Bailian Coding Plan API key (sk-sp-xxx)')
@click.option('--coding-plan-protocol', type=click.Choice(['openai', 'anthropic']), help='Coding Plan protocol')
@click.option('--thinking/--no-thinking', default=None, help='Enable/disable thinking mode')
@click.option('--thinking-budget', type=int, default=None, help='Max tokens for thinking (e.g. 10000)')
@click.option('--workdir', type=click.Path(exists=True), help='Working directory')
@click.option('--allow-root', 'extra_roots', multiple=True, type=click.Path(exists=True),
              help='Additional directory to allow file access (repeatable)')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def run(prompt, model, model_base_url, model_api_key, coding_plan_key, coding_plan_protocol, thinking, thinking_budget, workdir, extra_roots, verbose):
    """Run a single task with Cody

    Examples:
        cody run "create a hello.py file"
        cody run "refactor main.py to use async"
        cody run "写个单元测试" --model glm-4 --model-base-url https://open.bigmodel.cn/api/paas/v4/
        cody run "写个排序算法" --model qwen3.5 --coding-plan-key sk-sp-xxx
        cody run --workdir /proj/frontend --allow-root /proj/backend "sync configs"
    """
    if not prompt:
        console.print("[yellow]Please provide a prompt[/yellow]")
        console.print("Example: cody run 'create a hello.py file'")
        return

    workdir_path = Path(workdir) if workdir else Path.cwd()
    config = Config.load(workdir=workdir_path).apply_overrides(
        model=model,
        model_base_url=model_base_url,
        model_api_key=model_api_key,
        coding_plan_key=coding_plan_key,
        coding_plan_protocol=coding_plan_protocol,
        enable_thinking=thinking,
        thinking_budget=thinking_budget,
        extra_roots=list(extra_roots) or None,
    )

    runner = AgentRunner(config=config, workdir=workdir_path, extra_roots=[Path(r) for r in extra_roots])

    if verbose:
        console.print(f"[dim]Model: {config.model}[/dim]")
        console.print(f"[dim]Workdir: {runner.workdir}[/dim]")
        if config.enable_thinking:
            budget = f" (budget: {config.thinking_budget})" if config.thinking_budget else ""
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
@click.option('--model', help='AI model to use')
@click.option('--model-base-url', help='Custom OpenAI-compatible API base URL')
@click.option('--model-api-key', help='API key for custom model provider')
@click.option('--coding-plan-key', help='Aliyun Bailian Coding Plan API key (sk-sp-xxx)')
@click.option('--coding-plan-protocol', type=click.Choice(['openai', 'anthropic']), help='Coding Plan protocol')
@click.option('--thinking/--no-thinking', default=None, help='Enable/disable thinking mode')
@click.option('--thinking-budget', type=int, default=None, help='Max tokens for thinking (e.g. 10000)')
@click.option('--workdir', type=click.Path(exists=True), help='Working directory')
@click.option('--allow-root', 'extra_roots', multiple=True, type=click.Path(exists=True),
              help='Additional directory to allow file access (repeatable)')
@click.option('--session', 'session_id', default=None, help='Resume a session by ID')
@click.option('--continue', 'continue_last', is_flag=True, help='Continue last session')
def chat(model, model_base_url, model_api_key, coding_plan_key, coding_plan_protocol, thinking, thinking_budget, workdir, extra_roots, session_id, continue_last):
    """Interactive chat with Cody

    Start an interactive session where you can have a multi-turn conversation.

    Examples:
        cody chat
        cody chat --model anthropic:claude-sonnet-4-0
        cody chat --model glm-4 --model-base-url https://open.bigmodel.cn/api/paas/v4/
        cody chat --model qwen3.5 --coding-plan-key sk-sp-xxx
        cody chat --continue
        cody chat --session abc123
        cody chat --workdir /proj/frontend --allow-root /proj/backend
    """
    workdir_path = Path(workdir) if workdir else Path.cwd()

    config = Config.load(workdir=workdir_path).apply_overrides(
        model=model,
        model_base_url=model_base_url,
        model_api_key=model_api_key,
        coding_plan_key=coding_plan_key,
        coding_plan_protocol=coding_plan_protocol,
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
            model=config.model,
            workdir=str(workdir_path),
        )

    runner = AgentRunner(config=config, workdir=workdir_path, extra_roots=[Path(r) for r in extra_roots])

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

    # Start MCP servers before REPL
    asyncio.run(runner.start_mcp())

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

            # Run agent with streaming
            try:
                async def _stream_chat():
                    return await _render_stream(
                        runner.run_stream(user_input, message_history=message_history),
                    )

                result = asyncio.run(_stream_chat())

                # Update history for next turn
                if result:
                    message_history = result.all_messages()
                    store.add_message(session.id, "assistant", result.output)

            except Exception as e:
                console.print(f"\n[red]Error: {rich_escape(str(e))}[/red]\n")

    except Exception as e:
        console.print(f"[red]Fatal error: {rich_escape(str(e))}[/red]")
        sys.exit(1)
    finally:
        asyncio.run(runner.stop_mcp())
        asyncio.run(runner.stop_lsp())


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
    from .core.runner import AgentRunner
    return AgentRunner.messages_to_history(session.messages)


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
    workdir = Path.cwd()
    config = Config.load(workdir=workdir)
    runner = AgentRunner(config=config, workdir=workdir)

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
    workdir = Path.cwd()
    config = Config.load(workdir=workdir)
    runner = AgentRunner(config=config, workdir=workdir)

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
    workdir = Path.cwd()
    config = Config.load(workdir=workdir)
    runner = AgentRunner(config=config, workdir=workdir)

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
    workdir = Path.cwd()
    config = Config.load(workdir=workdir)
    runner = AgentRunner(config=config, workdir=workdir)

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
    cfg = Config.load(workdir=Path.cwd())
    console.print_json(cfg.model_dump_json(indent=2))


# ── TUI command ─────────────────────────────────────────────────────────────


@main.command()
@click.option('--model', help='AI model to use')
@click.option('--model-base-url', help='Custom OpenAI-compatible API base URL')
@click.option('--model-api-key', help='API key for custom model provider')
@click.option('--coding-plan-key', help='Aliyun Bailian Coding Plan API key (sk-sp-xxx)')
@click.option('--coding-plan-protocol', type=click.Choice(['openai', 'anthropic']), help='Coding Plan protocol')
@click.option('--thinking/--no-thinking', default=None, help='Enable/disable thinking mode')
@click.option('--thinking-budget', type=int, default=None, help='Max tokens for thinking (e.g. 10000)')
@click.option('--workdir', type=click.Path(exists=True), help='Working directory')
@click.option('--allow-root', 'extra_roots', multiple=True, type=click.Path(exists=True),
              help='Additional directory to allow file access (repeatable)')
@click.option('--session', 'session_id', default=None, help='Resume a session by ID')
@click.option('--continue', 'continue_last', is_flag=True, help='Continue last session')
def tui(model, model_base_url, model_api_key, coding_plan_key, coding_plan_protocol, thinking, thinking_budget, workdir, extra_roots, session_id, continue_last):
    """Launch interactive Terminal UI

    Full-screen terminal interface with streaming, session management, and keyboard shortcuts.

    Examples:
        cody tui
        cody tui --model anthropic:claude-sonnet-4-0
        cody tui --model glm-4 --model-base-url https://open.bigmodel.cn/api/paas/v4/
        cody tui --model qwen3.5 --coding-plan-key sk-sp-xxx
        cody tui --continue
        cody tui --workdir /proj/frontend --allow-root /proj/backend
    """
    from .tui import run_tui
    run_tui(
        model=model,
        model_base_url=model_base_url,
        model_api_key=model_api_key,
        coding_plan_key=coding_plan_key,
        coding_plan_protocol=coding_plan_protocol,
        thinking=thinking,
        thinking_budget=thinking_budget,
        workdir=workdir,
        extra_roots=list(extra_roots) or None,
        session_id=session_id,
        continue_last=continue_last,
    )


@config.command('set')
@click.argument('key')
@click.argument('value')
def config_set(key, value):
    """Set configuration value"""
    cfg = Config.load(workdir=Path.cwd())

    if key == 'model':
        cfg.model = value
    elif key == 'model_base_url':
        cfg.model_base_url = value
    elif key == 'model_api_key':
        console.print("[yellow]Warning: API keys should be set via CODY_MODEL_API_KEY env var[/yellow]")
        cfg.model_api_key = value
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
