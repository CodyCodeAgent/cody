"""CLI session management commands."""

from pathlib import Path

import click
from rich.markdown import Markdown
from rich.panel import Panel

from ...sdk.client import CodyClient
from ..utils import console


def _make_client() -> CodyClient:
    return CodyClient(workdir=str(Path.cwd()))


@click.group()
def sessions():
    """Manage chat sessions"""


@sessions.command('list')
@click.option('--limit', default=20, help='Number of sessions to show')
def sessions_list(limit):
    """List recent chat sessions"""
    client = _make_client()
    all_sessions = client.list_sessions(limit=limit)

    if not all_sessions:
        console.print("[yellow]No sessions found[/yellow]")
        return

    console.print("[bold]Recent sessions:[/bold]\n")
    for s in all_sessions:
        console.print(
            f"  [bold]{s.id}[/bold]  {s.title[:50]:<50}  "
            f"[dim]{s.message_count} msgs  {s.updated_at[:10]}[/dim]"
        )


@sessions.command('show')
@click.argument('session_id')
def sessions_show(session_id):
    """Show a session's conversation"""
    client = _make_client()
    try:
        session = client.get_session(session_id)
    except Exception:
        console.print(f"[red]Session not found: {session_id}[/red]")
        return

    console.print(
        Panel(
            f"Title: {session.title}\n"
            f"Model: {session.model}\n"
            f"Workdir: {session.workdir}\n"
            f"Created: {session.created_at[:19]}\n"
            f"Messages: {session.message_count}",
            title=f"[bold]Session {session.id}[/bold]",
            border_style="blue",
        )
    )

    for msg in session.messages:
        if msg["role"] == "user":
            console.print(f"\n[bold blue]You:[/bold blue] {msg['content']}")
        else:
            console.print("\n[bold green]Cody:[/bold green]")
            console.print(Markdown(msg["content"]))


@sessions.command('delete')
@click.argument('session_id')
@click.confirmation_option(prompt='Are you sure you want to delete this session?')
def sessions_delete(session_id):
    """Delete a chat session"""
    client = _make_client()
    try:
        client.delete_session(session_id)
        console.print(f"[green]Deleted session: {session_id}[/green]")
    except Exception:
        console.print(f"[red]Session not found: {session_id}[/red]")
