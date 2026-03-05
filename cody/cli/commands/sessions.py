"""CLI session management commands."""

import click
from rich.markdown import Markdown
from rich.panel import Panel

from ...core import SessionStore
from ..utils import console


@click.group()
def sessions():
    """Manage chat sessions"""


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
