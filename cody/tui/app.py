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
from ..core.prompt import Prompt
from ..sdk.client import AsyncCodyClient
from ..shared import (
    SPINNER_FRAMES, compact_message, auto_title, build_multimodal_prompt,
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
        max_tokens: Optional[int] = None,
        max_cost: Optional[float] = None,
        max_steps: Optional[int] = None,
    ) -> None:
        super().__init__()
        self._model_override = model
        self._thinking_override = thinking
        self._thinking_budget_override = thinking_budget
        self._workdir = (workdir or Path.cwd()).resolve()
        self._extra_roots: list[str] = extra_roots or []
        self._session_id_arg = session_id
        self._continue_last = continue_last
        self._max_tokens_override = max_tokens
        self._max_cost_override = max_cost
        self._max_steps_override = max_steps

        # Initialized in on_mount
        self._config: Optional[Config] = None
        self._client: Optional[AsyncCodyClient] = None
        self._session_id: Optional[str] = None
        self._message_history: list = []
        self._cancel_event: Optional[asyncio.Event] = None
        # Accumulated token usage for status line
        self._total_tokens: int = 0

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

        # Apply circuit breaker overrides
        if self._max_tokens_override is not None:
            self._config.circuit_breaker.max_tokens = self._max_tokens_override
        if self._max_cost_override is not None:
            self._config.circuit_breaker.max_cost_usd = self._max_cost_override
        if self._max_steps_override is not None:
            self._config.circuit_breaker.max_steps = self._max_steps_override

        self._client = AsyncCodyClient(
            workdir=str(self._workdir),
            model=self._config.model,
            api_key=self._config.model_api_key,
            base_url=self._config.model_base_url,
        )
        self._client.set_config(self._config)

        # Enable interaction so the AI can ask questions
        runner = self._client.get_runner()
        runner.config.interaction.enabled = True

        # Pending interaction request (set when AI asks a question)
        self._pending_interaction_request_id: Optional[str] = None

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
                await self._client.start_mcp()
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
        tokens_str = f"  |  Tokens: {self._total_tokens:,}" if self._total_tokens else ""
        self.query_one("#status-line", StatusLine).update(
            f" Session: {sid}  |  Model: {model}  |  "
            f"Dir: {self._workdir.name}  |  Messages: {msg_count}{tokens_str}"
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
        "/skills": "List available skills",
        "/settings": "Show/change settings",
        "/image": "Send image with message",
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

        # If there's a pending interaction request, submit the response
        if self._pending_interaction_request_id and self._client:
            request_id = self._pending_interaction_request_id
            self._pending_interaction_request_id = None
            # Restore placeholder and disable input (agent is running)
            inp = self.query_one("#prompt-input", Input)
            inp.placeholder = "Type a message... (Enter to send)"
            self._set_input_enabled(False)
            self._set_processing_state("Processing...")
            # Show the answer in the active stream bubble
            try:
                stream = self.query_one("#active-stream", StreamBubble)
                stream.append(f"[dim]→ {text}[/dim]\n")
            except NoMatches:
                pass
            await self._client.submit_interaction(
                request_id=request_id,
                action="answer",
                content=text,
            )
            return

        # Handle slash commands
        if text.startswith("/"):
            self._handle_command(text)
            return

        # Show user message
        self._add_bubble("user", text)

        # Auto-title (before stream, which auto-saves user message)
        assert self._session_id is not None
        if self._client and self._client.get_message_count(self._session_id) == 0:
            self._client.update_title(self._session_id, auto_title(text))

        # Run agent — SDK auto-saves user+assistant messages via session
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
            self._processing_timer = None  # type: ignore[assignment]
        self._update_status()

    @work(thread=False)
    async def _run_agent(self, prompt: Prompt) -> None:
        """Stream agent response via SDK StreamChunk API."""
        assert self._session_id is not None
        self.is_running = True
        self._set_input_enabled(False)
        self._cancel_event = asyncio.Event()

        bubble = self._add_stream_bubble()

        # Start processing indicator on status line
        self._start_processing()

        try:
            assert self._client is not None
            async for chunk in self._client.stream(
                prompt, session_id=self._session_id,
                cancel_event=self._cancel_event,
            ):
                if chunk.type == "cancelled":
                    bubble.append("\n\n[dim italic](cancelled)[/dim italic]")
                    break

                if chunk.type == "compact":
                    self._add_bubble(
                        "system",
                        f"[yellow]{compact_message(chunk.original_messages, chunk.compacted_messages, chunk.estimated_tokens_saved)}[/yellow]",
                    )
                elif chunk.type == "thinking":
                    bubble.append(f"[dim]{chunk.content}[/dim]")
                elif chunk.type == "tool_call":
                    tool_name = chunk.tool_name or ""
                    self._set_processing_state(f"Running {tool_name}...")
                    args = chunk.args or {}
                    args_str = ", ".join(
                        f"{k}={_truncate_repr(v)}"
                        for k, v in list(args.items())[:3]
                    )
                    bubble.append(f"\n[dim]→ {tool_name}({args_str})[/dim]\n")
                elif chunk.type == "tool_result":
                    self._set_processing_state("Generating...")
                    result_len = len(chunk.content) if chunk.content else 0
                    tool_name = chunk.tool_name or ""
                    bubble.append(
                        f"[dim]✓ {tool_name} done ({result_len} chars)[/dim]\n"
                    )
                elif chunk.type == "interaction_request":
                    self._set_processing_state("Waiting for your answer...")
                    # Display the question in the stream bubble
                    prompt_text = chunk.content or "AI is asking a question"
                    bubble.append(f"\n[bold yellow]? {prompt_text}[/bold yellow]\n")
                    if chunk.options:
                        for i, opt in enumerate(chunk.options, 1):
                            bubble.append(f"  [cyan]{i})[/cyan] {opt}\n")
                    # Enable input and store the request ID so on_input_submitted
                    # can respond to this interaction
                    self._pending_interaction_request_id = chunk.request_id
                    self._set_input_enabled(True)
                    inp = self.query_one("#prompt-input", Input)
                    inp.placeholder = "Type your answer and press Enter..."
                    inp.focus()
                    # Pause streaming — the stream will resume automatically
                    # when submit_interaction resolves the Future
                elif chunk.type == "text_delta":
                    self._set_processing_state("Generating...")
                    bubble.append(chunk.content)
                elif chunk.type == "done":
                    # Update message history from SDK stream
                    self._message_history = chunk.message_history or []
                    # Accumulate token usage for status line
                    if chunk.usage:
                        self._total_tokens += chunk.usage.total_tokens

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

    def _handle_command(self, raw_cmd: str) -> None:
        parts = raw_cmd.strip().split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit", "/q"):
            self.exit()
        elif cmd == "/new":
            self.action_new_session()
        elif cmd == "/sessions":
            self._show_sessions()
        elif cmd == "/skills":
            self._show_skills(arg)
        elif cmd == "/settings":
            self._handle_settings(arg)
        elif cmd == "/image":
            self._handle_image_command(arg)
        elif cmd == "/clear":
            scroll = self.query_one("#chat-scroll", VerticalScroll)
            scroll.remove_children()
            self._add_bubble("system", "[dim]Screen cleared. Session continues.[/dim]")
        elif cmd == "/help":
            self._add_bubble(
                "system",
                "[bold]Commands:[/bold]\n"
                "  /new             — Start a new session\n"
                "  /sessions        — List recent sessions\n"
                "  /skills          — List available skills\n"
                "  /skills enable X — Enable a skill\n"
                "  /skills disable X — Disable a skill\n"
                "  /settings        — Show current settings\n"
                "  /settings model X — Change model\n"
                "  /settings thinking on/off — Toggle thinking\n"
                "  /image path msg  — Send image with message\n"
                "  /clear           — Clear screen\n"
                "  /quit            — Exit\n"
                "  /help            — Show this help\n\n"
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

    def _show_skills(self, arg: str) -> None:
        if not self._client:
            return
        runner = self._client.get_runner()
        sm = runner.skill_manager

        # Sub-commands: enable / disable
        if arg.startswith("enable "):
            name = arg[7:].strip()
            sm.enable_skill(name)
            self._add_bubble("system", f"[green]Skill enabled: {name}[/green]")
            return
        if arg.startswith("disable "):
            name = arg[8:].strip()
            sm.disable_skill(name)
            self._add_bubble("system", f"[yellow]Skill disabled: {name}[/yellow]")
            return

        # List skills
        skills = sm.list_skills()
        if not skills:
            self._add_bubble("system", "[yellow]No skills found[/yellow]")
            return
        lines = ["[bold]Available skills:[/bold]"]
        for s in skills:
            status = "[green]on[/green]" if s.enabled else "[dim]off[/dim]"
            lines.append(f"  {status}  {s.name}  [dim]{s.description}[/dim]")
        self._add_bubble("system", "\n".join(lines))

    def _handle_settings(self, arg: str) -> None:
        if not self._config:
            return

        if not arg:
            # Show current settings
            cb = self._config.circuit_breaker
            lines = [
                "[bold]Current settings:[/bold]",
                f"  Model: {self._config.model}",
                f"  Thinking: {'on' if self._config.enable_thinking else 'off'}",
            ]
            if self._config.thinking_budget:
                lines.append(f"  Thinking budget: {self._config.thinking_budget}")
            lines.extend([
                f"  Circuit breaker: max_tokens={cb.max_tokens}, "
                f"max_cost=${cb.max_cost_usd}, max_steps={cb.max_steps}",
                f"  Tokens used (session): {self._total_tokens:,}",
            ])
            self._add_bubble("system", "\n".join(lines))
            return

        parts = arg.split(None, 1)
        key = parts[0].lower()
        val = parts[1].strip() if len(parts) > 1 else ""

        if key == "model" and val:
            self._config.model = val
            # Rebuild the runner so the new model takes effect
            if self._client:
                self._client.set_config(self._config)
            self._add_bubble("system", f"[green]Model changed to: {val}[/green]")
            self._update_status()
        elif key == "thinking" and val:
            enabled = val.lower() in ("on", "true", "1", "yes")
            self._config.enable_thinking = enabled
            if self._client:
                self._client.get_runner().config.enable_thinking = enabled
            self._add_bubble(
                "system",
                f"[green]Thinking {'enabled' if enabled else 'disabled'}[/green]",
            )
        else:
            self._add_bubble(
                "system",
                "[yellow]Usage: /settings, /settings model <name>, "
                "/settings thinking on|off[/yellow]",
            )

    def _handle_image_command(self, arg: str) -> None:
        """Handle /image <path> <message> command to send an image with a prompt."""
        if not arg:
            self._add_bubble(
                "system", "[yellow]Usage: /image <path> <message>[/yellow]"
            )
            return

        parts = arg.split(None, 1)
        image_path = Path(parts[0])
        message = parts[1] if len(parts) > 1 else "Describe this image"

        if not image_path.exists():
            self._add_bubble("system", f"[red]File not found: {image_path}[/red]")
            return

        prompt = build_multimodal_prompt(message, [str(image_path)])

        self._add_bubble("user", f"{message}\n[dim](image: {image_path.name})[/dim]")

        # Auto-title
        assert self._session_id is not None
        if self._client and self._client.get_message_count(self._session_id) == 0:
            self._client.update_title(self._session_id, auto_title(message))

        self._run_agent(prompt)

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
    max_tokens: Optional[int] = None,
    max_cost: Optional[float] = None,
    max_steps: Optional[int] = None,
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
        max_tokens=max_tokens,
        max_cost=max_cost,
        max_steps=max_steps,
    )
    app.run()
