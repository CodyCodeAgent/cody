"""TUI main application for Cody."""

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

try:
    from textual import work
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import VerticalScroll
    from textual.css.query import NoMatches
    from textual.reactive import reactive
    from textual.widgets import Header, Input
except ImportError:
    raise SystemExit(
        "TUI requires extra dependencies. Install with:\n"
        "  pip install cody-ai[tui]"
    )

from ..core import Config
from ..sdk.client import AsyncCodyClient
from ..shared import (
    SPINNER_FRAMES, compact_message, auto_title,
    format_elapsed, format_session_line, truncate_repr as _truncate_repr,
)
from .widgets import MessageBubble, StreamBubble, StatusLine

logger = logging.getLogger(__name__)


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
        margin: 0 2;
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
        thinking: Optional[bool] = None,
        thinking_budget: Optional[int] = None,
        workdir: Optional[Path] = None,
        extra_roots: Optional[list[str]] = None,
        session_id: Optional[str] = None,
        continue_last: bool = False,
    ) -> None:
        super().__init__()
        self._model_override = model
        self._thinking_override = thinking
        self._thinking_budget_override = thinking_budget
        self._workdir = (workdir or Path.cwd()).resolve()
        self._extra_roots: list[str] = extra_roots or []
        self._session_id_arg = session_id
        self._continue_last = continue_last

        # Initialized in on_mount
        self._config: Optional[Config] = None
        self._client: Optional[AsyncCodyClient] = None
        self._session_id: Optional[str] = None
        self._message_history: list = []
        self._cancel_event: Optional[asyncio.Event] = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="chat-scroll")
        yield StatusLine(id="status-line")
        yield Input(placeholder="Type a message... (Enter to send)", id="prompt-input")

    def on_mount(self) -> None:
        self._config = Config.load(workdir=self._workdir).apply_overrides(
            model=self._model_override,
            enable_thinking=self._thinking_override,
            thinking_budget=self._thinking_budget_override,
            extra_roots=self._extra_roots or None,
        )

        self._client = AsyncCodyClient(
            workdir=str(self._workdir),
            model=self._config.model,
            api_key=self._config.model_api_key,
            base_url=self._config.model_base_url,
        )
        self._client.set_config(self._config)

        store = self._client.get_session_store()

        # Resolve or create session
        session = None
        if self._session_id_arg:
            session = store.get_session(self._session_id_arg)
        elif self._continue_last:
            session = store.get_latest_session(workdir=str(self._workdir))

        if session is None:
            session = store.create_session(
                title="TUI session",
                model=self._config.model,
                workdir=str(self._workdir),
            )

        self._session_id = session.id

        # Load existing messages
        for msg in session.messages:
            self._add_bubble(msg.role, msg.content)

        self._message_history = AsyncCodyClient.messages_to_history(session.messages)
        self._update_status()
        self.query_one("#prompt-input", Input).focus()

        # Start MCP servers if configured
        self._start_services()

    @work(thread=False)
    async def _start_services(self) -> None:
        """Start MCP servers in the background."""
        if self._client:
            try:
                runner = self._client.get_runner()
                await runner.start_mcp()
            except Exception:
                logger.debug("MCP start failed", exc_info=True)

    async def _stop_services(self) -> None:
        """Stop MCP and LSP servers."""
        if self._client:
            try:
                await self._client.close()
            except Exception:
                logger.debug("Service stop failed", exc_info=True)

    # ── UI helpers ───────────────────────────────────────────────────────────

    _MAX_BUBBLES = 200

    def _add_bubble(self, role: str, content: str) -> MessageBubble:
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        # Recycle old bubbles to keep widget tree lightweight
        bubbles = scroll.query(MessageBubble)
        if len(bubbles) >= self._MAX_BUBBLES:
            for old in list(bubbles)[: len(bubbles) - self._MAX_BUBBLES + 1]:
                old.remove()
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
            self._client.get_message_count(self._session_id)
            if self._client and self._session_id
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
        assert self._session_id is not None
        if self._client and self._client.get_message_count(self._session_id) == 0:
            self._client.update_title(self._session_id, auto_title(text))

        # Save user message
        if self._client:
            self._client.add_message(self._session_id, "user", text)

        # Run agent
        self._run_agent(text)

    _SPINNER_FRAMES = SPINNER_FRAMES

    # ── Processing status indicator ──────────────────────────────────────────

    def _start_processing(self) -> None:
        """Start a processing indicator on the status line with elapsed time."""
        self._processing_start = time.monotonic()
        self._processing_state = "Thinking..."
        self._processing_idx = 0
        self._processing_timer = self.set_interval(0.1, self._tick_processing)

    def _tick_processing(self) -> None:
        """Update the status line spinner with current state and elapsed time."""
        elapsed = time.monotonic() - self._processing_start
        frame = self._SPINNER_FRAMES[self._processing_idx % len(self._SPINNER_FRAMES)]
        self._processing_idx += 1
        self.query_one("#status-line", StatusLine).update(
            f" {frame} {self._processing_state} ({format_elapsed(elapsed)})"
        )

    def _set_processing_state(self, state: str) -> None:
        """Update the processing status text (e.g. 'Running read_file...')."""
        self._processing_state = state

    def _stop_processing(self) -> None:
        """Stop the processing indicator and restore normal status line."""
        if hasattr(self, '_processing_timer') and self._processing_timer is not None:
            self._processing_timer.stop()
            self._processing_timer = None
        self._update_status()

    @work(thread=False)
    async def _run_agent(self, prompt: str) -> None:
        """Stream agent response with structured events."""
        from ..core.runner import (
            CompactEvent, ThinkingEvent, TextDeltaEvent, ToolCallEvent,
            ToolResultEvent, DoneEvent,
        )

        assert self._session_id is not None
        self.is_running = True
        self._set_input_enabled(False)
        self._cancel_event = asyncio.Event()

        bubble = self._add_stream_bubble()

        # Start processing indicator on status line
        self._start_processing()

        try:
            assert self._client is not None
            runner = self._client.get_runner()
            async for event in runner.run_stream(
                prompt, message_history=self._message_history
            ):
                if self._cancel_event.is_set():
                    bubble.append("\n\n[dim italic](cancelled)[/dim italic]")
                    break

                if isinstance(event, CompactEvent):
                    self._add_bubble(
                        "system",
                        f"[yellow]{compact_message(event.original_messages, event.compacted_messages, event.estimated_tokens_saved)}[/yellow]",
                    )
                elif isinstance(event, ThinkingEvent):
                    bubble.append(f"[dim]{event.content}[/dim]")
                elif isinstance(event, ToolCallEvent):
                    self._set_processing_state(f"Running {event.tool_name}...")
                    args_str = ", ".join(
                        f"{k}={_truncate_repr(v)}"
                        for k, v in list(event.args.items())[:3]
                    )
                    bubble.append(f"\n[dim]→ {event.tool_name}({args_str})[/dim]\n")
                elif isinstance(event, ToolResultEvent):
                    self._set_processing_state("Generating...")
                    result_len = len(event.result) if event.result else 0
                    bubble.append(
                        f"[dim]✓ {event.tool_name} done ({result_len} chars)[/dim]\n"
                    )
                elif isinstance(event, TextDeltaEvent):
                    self._set_processing_state("Generating...")
                    bubble.append(event.content)
                elif isinstance(event, DoneEvent):
                    # Use real message history from pydantic-ai (includes tool calls)
                    self._message_history = event.result.all_messages()
                    # Save assistant message
                    if self._client and not self._cancel_event.is_set():
                        self._client.add_message(
                            self._session_id, "assistant", event.result.output
                        )

        except Exception as e:
            bubble.append(f"\n\n[bold red]Error: {e}[/bold red]")

        finally:
            self._stop_processing()
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
        if not self._client:
            return
        store = self._client.get_session_store()
        sessions = store.list_sessions(limit=10)
        if not sessions:
            self._add_bubble("system", "[yellow]No sessions found[/yellow]")
            return

        lines = ["[bold]Recent sessions:[/bold]"]
        for s in sessions:
            count = self._client.get_message_count(s.id)
            line = format_session_line(
                s.id, s.title, count, s.updated_at, self._session_id or ""
            )
            lines.append(f"[dim]{line}[/dim]")
        self._add_bubble("system", "\n".join(lines))

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_new_session(self) -> None:
        if not self._client or not self._config:
            return

        store = self._client.get_session_store()
        session = store.create_session(
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
    thinking: Optional[bool] = None,
    thinking_budget: Optional[int] = None,
    workdir: Optional[str] = None,
    extra_roots: Optional[list[str]] = None,
    session_id: Optional[str] = None,
    continue_last: bool = False,
) -> None:
    """Launch the Cody TUI.

    Config readiness is checked by the CLI caller before launching.
    """
    workdir_path = Path(workdir) if workdir else None
    app = CodyTUI(
        model=model,
        thinking=thinking,
        thinking_budget=thinking_budget,
        workdir=workdir_path,
        extra_roots=extra_roots,
        session_id=session_id,
        continue_last=continue_last,
    )
    app.run()
