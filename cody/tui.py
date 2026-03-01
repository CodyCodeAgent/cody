"""Terminal UI for Cody — interactive AI coding assistant"""

import asyncio
import time
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
        background: $panel;
        color: $text;
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
        coding_plan_key: Optional[str] = None,
        coding_plan_protocol: Optional[str] = None,
        thinking: Optional[bool] = None,
        thinking_budget: Optional[int] = None,
        workdir: Optional[Path] = None,
        session_id: Optional[str] = None,
        continue_last: bool = False,
    ) -> None:
        super().__init__()
        self._model_override = model
        self._model_base_url_override = model_base_url
        self._model_api_key_override = model_api_key
        self._coding_plan_key_override = coding_plan_key
        self._coding_plan_protocol_override = coding_plan_protocol
        self._thinking_override = thinking
        self._thinking_budget_override = thinking_budget
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
        self._config = Config.load(workdir=self._workdir).apply_overrides(
            model=self._model_override,
            model_base_url=self._model_base_url_override,
            model_api_key=self._model_api_key_override,
            coding_plan_key=self._coding_plan_key_override,
            coding_plan_protocol=self._coding_plan_protocol_override,
            enable_thinking=self._thinking_override,
            thinking_budget=self._thinking_budget_override,
        )

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

        # Start MCP servers if configured
        self._start_services()

    @work(thread=False)
    async def _start_services(self) -> None:
        """Start MCP servers in the background."""
        if self._runner:
            try:
                await self._runner.start_mcp()
            except Exception:
                pass

    async def _stop_services(self) -> None:
        """Stop MCP and LSP servers."""
        if self._runner:
            try:
                await self._runner.stop_mcp()
                await self._runner.stop_lsp()
            except Exception:
                pass

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

    # ── Slash command hints ────────────────────────────────────────────────

    _COMMANDS = {
        "/new": "Start a new session",
        "/sessions": "List recent sessions",
        "/clear": "Clear screen",
        "/help": "Show help",
        "/quit": "Exit",
    }

    def on_input_changed(self, event: Input.Changed) -> None:
        """Show command hints in status line when input starts with /."""
        text = event.value
        if text.startswith("/"):
            prefix = text.strip().lower()
            matches = [
                f"{cmd} [dim]{desc}[/dim]"
                for cmd, desc in self._COMMANDS.items()
                if cmd.startswith(prefix)
            ]
            if matches:
                self.query_one("#status-line", StatusLine).update(
                    " " + "  |  ".join(matches)
                )
            else:
                self.query_one("#status-line", StatusLine).update(
                    f" [yellow]Unknown command: {text}[/yellow]"
                )
        else:
            self._update_status()

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

    _SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def _start_tool_spinner(self, tool_name: str) -> None:
        """Start a spinner on the status line during tool execution."""
        self._tool_executing = tool_name
        self._tool_start = time.monotonic()
        self._tool_spinner_idx = 0
        self._tool_timer = self.set_interval(0.1, self._tick_tool_spinner)

    def _tick_tool_spinner(self) -> None:
        """Update the status line with spinner animation."""
        elapsed = time.monotonic() - self._tool_start
        frame = self._SPINNER_FRAMES[self._tool_spinner_idx % len(self._SPINNER_FRAMES)]
        self.query_one("#status-line", StatusLine).update(
            f" {frame} {self._tool_executing} running... ({elapsed:.0f}s)"
        )
        self._tool_spinner_idx += 1

    def _stop_tool_spinner(self) -> None:
        """Stop the tool spinner and restore the status line."""
        if hasattr(self, '_tool_timer') and self._tool_timer is not None:
            self._tool_timer.stop()
            self._tool_timer = None
            self._update_status()

    @work(thread=False)
    async def _run_agent(self, prompt: str) -> None:
        """Stream agent response with structured events."""
        from cody.core.runner import (
            CompactEvent, ThinkingEvent, TextDeltaEvent, ToolCallEvent,
            ToolResultEvent, DoneEvent,
        )

        self.is_running = True
        self._set_input_enabled(False)
        self._cancel_event = asyncio.Event()
        self._tool_timer = None

        bubble = self._add_stream_bubble()
        scroll = self.query_one("#chat-scroll", VerticalScroll)

        try:
            async for event in self._runner.run_stream(
                prompt, message_history=self._message_history
            ):
                if self._cancel_event.is_set():
                    bubble.append("\n\n[dim italic](cancelled)[/dim italic]")
                    break

                if isinstance(event, CompactEvent):
                    self._add_bubble(
                        "system",
                        f"[yellow]⚡ 上下文已压缩："
                        f"{event.original_messages} → {event.compacted_messages} 条消息，"
                        f"节省约 ~{event.estimated_tokens_saved} tokens[/yellow]",
                    )
                elif isinstance(event, ThinkingEvent):
                    bubble.append(f"[dim]{event.content}[/dim]")
                    scroll.scroll_end(animate=False)
                elif isinstance(event, ToolCallEvent):
                    self._stop_tool_spinner()
                    args_str = ", ".join(f"{k}={v!r}" for k, v in list(event.args.items())[:3])
                    bubble.append(f"\n[dim]→ {event.tool_name}({args_str})[/dim]\n")
                    scroll.scroll_end(animate=False)
                    self._start_tool_spinner(event.tool_name)
                elif isinstance(event, ToolResultEvent):
                    self._stop_tool_spinner()
                elif isinstance(event, TextDeltaEvent):
                    self._stop_tool_spinner()
                    bubble.append(event.content)
                    scroll.scroll_end(animate=False)
                elif isinstance(event, DoneEvent):
                    self._stop_tool_spinner()
                    # Use real message history from pydantic-ai (includes tool calls)
                    self._message_history = event.result.all_messages()
                    # Save assistant message
                    if self._store and not self._cancel_event.is_set():
                        self._store.add_message(
                            self._session_id, "assistant", event.result.output
                        )

        except Exception as e:
            bubble.append(f"\n\n[bold red]Error: {e}[/bold red]")

        finally:
            self._stop_tool_spinner()
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

    async def on_unmount(self) -> None:
        """Clean up MCP/LSP servers on app exit."""
        await self._stop_services()


# ── Entry point ──────────────────────────────────────────────────────────────


def run_tui(
    model: Optional[str] = None,
    model_base_url: Optional[str] = None,
    model_api_key: Optional[str] = None,
    coding_plan_key: Optional[str] = None,
    coding_plan_protocol: Optional[str] = None,
    thinking: Optional[bool] = None,
    thinking_budget: Optional[int] = None,
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
        coding_plan_key=coding_plan_key,
        coding_plan_protocol=coding_plan_protocol,
        thinking=thinking,
        thinking_budget=thinking_budget,
        workdir=workdir_path,
        session_id=session_id,
        continue_last=continue_last,
    )
    app.run()
