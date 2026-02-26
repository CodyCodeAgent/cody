"""Terminal UI for Cody — interactive AI coding assistant"""

import asyncio
from pathlib import Path
from typing import Optional

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import Footer, Header, Input, Static

from .core import AgentRunner, Config, SessionStore


# ── Widgets ──────────────────────────────────────────────────────────────────


class MessageBubble(Static):
    """A single chat message displayed in the conversation."""

    def __init__(self, role: str, content: str, **kwargs) -> None:
        self.role = role
        self.content_text = content
        super().__init__(self._format_message(role, content), **kwargs)

    @staticmethod
    def _format_message(role: str, content: str) -> str:
        if role == "user":
            return f"[bold dodger_blue1]You[/bold dodger_blue1]\n{content}"
        elif role == "assistant":
            return f"[bold green]Cody[/bold green]\n{content}"
        else:
            return f"[bold yellow]{role}[/bold yellow]\n{content}"


class StreamBubble(Static):
    """A message bubble that accumulates streamed text."""

    def __init__(self, **kwargs) -> None:
        super().__init__("[bold green]Cody[/bold green]\n", **kwargs)
        self._chunks: list[str] = []

    def append(self, text: str) -> None:
        self._chunks.append(text)
        full = "".join(self._chunks)
        self.update(f"[bold green]Cody[/bold green]\n{full}")

    @property
    def full_text(self) -> str:
        return "".join(self._chunks)


class StatusLine(Static):
    """Bottom status line showing session/model info."""
    pass


# ── Main App ─────────────────────────────────────────────────────────────────


class CodyTUI(App):
    """Cody Terminal UI — interactive AI coding assistant."""

    TITLE = "Cody"
    CSS = """
    Screen {
        background: $surface;
    }

    #chat-scroll {
        height: 1fr;
        scrollbar-size: 1 1;
    }

    MessageBubble {
        margin: 1 2;
        padding: 1 2;
    }

    StreamBubble {
        margin: 1 2;
        padding: 1 2;
    }

    #prompt-input {
        dock: bottom;
        margin: 0 2 1 2;
    }

    #status-line {
        dock: bottom;
        height: 1;
        background: $primary-background;
        color: $text-muted;
        padding: 0 2;
    }
    """

    BINDINGS = [
        Binding("ctrl+n", "new_session", "New session"),
        Binding("ctrl+c", "cancel_or_quit", "Cancel/Quit", show=True, priority=True),
        Binding("ctrl+q", "quit_app", "Quit"),
    ]

    is_running: reactive[bool] = reactive(False)

    def __init__(
        self,
        model: Optional[str] = None,
        model_base_url: Optional[str] = None,
        model_api_key: Optional[str] = None,
        workdir: Optional[Path] = None,
        session_id: Optional[str] = None,
        continue_last: bool = False,
    ) -> None:
        super().__init__()
        self._model_override = model
        self._model_base_url_override = model_base_url
        self._model_api_key_override = model_api_key
        self._workdir = (workdir or Path.cwd()).resolve()
        self._session_id_arg = session_id
        self._continue_last = continue_last

        # Initialized in on_mount
        self._config: Optional[Config] = None
        self._runner: Optional[AgentRunner] = None
        self._store: Optional[SessionStore] = None
        self._session_id: Optional[str] = None
        self._message_history: list = []
        self._cancel_event: Optional[asyncio.Event] = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="chat-scroll")
        yield StatusLine(id="status-line")
        yield Input(placeholder="Type a message... (Enter to send)", id="prompt-input")
        yield Footer()

    def on_mount(self) -> None:
        self._config = Config.load()
        if self._model_override:
            self._config.model = self._model_override
        if self._model_base_url_override:
            self._config.model_base_url = self._model_base_url_override
        if self._model_api_key_override:
            self._config.model_api_key = self._model_api_key_override

        self._runner = AgentRunner(config=self._config, workdir=self._workdir)
        self._store = SessionStore()

        # Resolve or create session
        session = None
        if self._session_id_arg:
            session = self._store.get_session(self._session_id_arg)
        elif self._continue_last:
            session = self._store.get_latest_session(workdir=str(self._workdir))

        if session is None:
            session = self._store.create_session(
                title="TUI session",
                model=self._config.model,
                workdir=str(self._workdir),
            )

        self._session_id = session.id

        # Load existing messages
        for msg in session.messages:
            self._add_bubble(msg.role, msg.content)

        self._message_history = AgentRunner.messages_to_history(session.messages)
        self._update_status()
        self.query_one("#prompt-input", Input).focus()

    # ── UI helpers ───────────────────────────────────────────────────────────

    def _add_bubble(self, role: str, content: str) -> MessageBubble:
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        bubble = MessageBubble(role, content)
        scroll.mount(bubble)
        scroll.scroll_end(animate=False)
        return bubble

    def _add_stream_bubble(self) -> StreamBubble:
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        bubble = StreamBubble(id="active-stream")
        scroll.mount(bubble)
        scroll.scroll_end(animate=False)
        return bubble

    def _update_status(self) -> None:
        model = self._config.model if self._config else "?"
        sid = self._session_id or "?"
        msg_count = (
            self._store.get_message_count(self._session_id)
            if self._store and self._session_id
            else 0
        )
        self.query_one("#status-line", StatusLine).update(
            f" Session: {sid}  |  Model: {model}  |  "
            f"Dir: {self._workdir.name}  |  Messages: {msg_count}"
        )

    def _set_input_enabled(self, enabled: bool) -> None:
        inp = self.query_one("#prompt-input", Input)
        inp.disabled = not enabled
        if enabled:
            inp.focus()

    # ── Input handling ───────────────────────────────────────────────────────

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return

        event.input.clear()

        # Handle slash commands
        if text.startswith("/"):
            self._handle_command(text)
            return

        # Show user message
        self._add_bubble("user", text)

        # Auto-title
        if self._store and self._store.get_message_count(self._session_id) == 0:
            title = text[:60].strip()
            if len(text) > 60:
                title += "..."
            self._store.update_title(self._session_id, title)

        # Save user message
        if self._store:
            self._store.add_message(self._session_id, "user", text)

        # Run agent
        self._run_agent(text)

    @work(thread=False)
    async def _run_agent(self, prompt: str) -> None:
        """Stream agent response in background."""
        self.is_running = True
        self._set_input_enabled(False)
        self._cancel_event = asyncio.Event()

        bubble = self._add_stream_bubble()
        scroll = self.query_one("#chat-scroll", VerticalScroll)

        try:
            async for chunk in self._runner.run_stream(
                prompt, message_history=self._message_history
            ):
                if self._cancel_event.is_set():
                    bubble.append("\n\n[dim italic](cancelled)[/dim italic]")
                    break
                bubble.append(chunk)
                scroll.scroll_end(animate=False)

            # Get full response
            response_text = bubble.full_text

            # Update history — re-run non-streaming to get proper message objects
            # For simplicity, manually append to history
            from pydantic_ai.messages import (
                ModelRequest,
                ModelResponse,
                TextPart,
                UserPromptPart,
            )
            self._message_history.append(
                ModelRequest(parts=[UserPromptPart(content=prompt)])
            )
            self._message_history.append(
                ModelResponse(parts=[TextPart(content=response_text)])
            )

            # Save assistant message
            if self._store and not self._cancel_event.is_set():
                self._store.add_message(self._session_id, "assistant", response_text)

        except Exception as e:
            bubble.append(f"\n\n[bold red]Error: {e}[/bold red]")

        finally:
            # Replace StreamBubble with static MessageBubble
            try:
                stream = self.query_one("#active-stream", StreamBubble)
                final_text = stream.full_text
                stream.remove()
                self._add_bubble("assistant", final_text)
            except NoMatches:
                pass

            self.is_running = False
            self._cancel_event = None
            self._set_input_enabled(True)
            self._update_status()

    # ── Commands ─────────────────────────────────────────────────────────────

    def _handle_command(self, cmd: str) -> None:
        cmd = cmd.strip().lower()

        if cmd in ("/quit", "/exit", "/q"):
            self.exit()
        elif cmd == "/new":
            self.action_new_session()
        elif cmd == "/sessions":
            self._show_sessions()
        elif cmd == "/clear":
            scroll = self.query_one("#chat-scroll", VerticalScroll)
            scroll.remove_children()
            self._add_bubble("system", "[dim]Screen cleared. Session continues.[/dim]")
        elif cmd == "/help":
            self._add_bubble(
                "system",
                "[bold]Commands:[/bold]\n"
                "  /new      — Start a new session\n"
                "  /sessions — List recent sessions\n"
                "  /clear    — Clear screen\n"
                "  /quit     — Exit\n"
                "  /help     — Show this help\n\n"
                "[bold]Shortcuts:[/bold]\n"
                "  Ctrl+N — New session\n"
                "  Ctrl+C — Cancel running / Quit\n"
                "  Ctrl+Q — Quit",
            )
        else:
            self._add_bubble("system", f"[yellow]Unknown command: {cmd}[/yellow]\nType /help")

    def _show_sessions(self) -> None:
        if not self._store:
            return
        sessions = self._store.list_sessions(limit=10)
        if not sessions:
            self._add_bubble("system", "[yellow]No sessions found[/yellow]")
            return

        lines = ["[bold]Recent sessions:[/bold]"]
        for s in sessions:
            count = self._store.get_message_count(s.id)
            marker = " [green]<< current[/green]" if s.id == self._session_id else ""
            lines.append(
                f"  {s.id}  {s.title[:40]:<40}  "
                f"[dim]{count} msgs  {s.updated_at[:10]}[/dim]{marker}"
            )
        self._add_bubble("system", "\n".join(lines))

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_new_session(self) -> None:
        if not self._store or not self._config:
            return

        session = self._store.create_session(
            title="TUI session",
            model=self._config.model,
            workdir=str(self._workdir),
        )
        self._session_id = session.id
        self._message_history = []

        scroll = self.query_one("#chat-scroll", VerticalScroll)
        scroll.remove_children()
        self._add_bubble("system", f"[green]New session created: {session.id}[/green]")
        self._update_status()

    def action_cancel_or_quit(self) -> None:
        if self.is_running and self._cancel_event:
            self._cancel_event.set()
        else:
            self.exit()

    def action_quit_app(self) -> None:
        self.exit()


# ── Entry point ──────────────────────────────────────────────────────────────


def run_tui(
    model: Optional[str] = None,
    model_base_url: Optional[str] = None,
    model_api_key: Optional[str] = None,
    workdir: Optional[str] = None,
    session_id: Optional[str] = None,
    continue_last: bool = False,
) -> None:
    """Launch the Cody TUI."""
    workdir_path = Path(workdir) if workdir else None
    app = CodyTUI(
        model=model,
        model_base_url=model_base_url,
        model_api_key=model_api_key,
        workdir=workdir_path,
        session_id=session_id,
        continue_last=continue_last,
    )
    app.run()
