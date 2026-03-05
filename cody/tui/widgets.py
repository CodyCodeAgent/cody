"""TUI widget classes for Cody."""

try:
    from textual.widgets import Static
except ImportError:
    raise SystemExit(
        "TUI requires extra dependencies. Install with:\n"
        "  pip install cody-ai[tui]"
    )


def _truncate_repr(value: object, max_len: int = 120) -> str:
    """Truncate repr of a value to max_len characters."""
    s = repr(value)
    if len(s) <= max_len:
        return s
    return s[:max_len] + f"...({len(s)} chars)"


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
        if role == "assistant":
            return f"[bold green]Cody[/bold green]\n{content}"
        return f"[bold yellow]{role}[/bold yellow]\n{content}"


class StreamBubble(Static):
    """A message bubble that accumulates streamed text with batched rendering."""

    def __init__(self, **kwargs) -> None:
        super().__init__("[bold green]Cody[/bold green]\n", **kwargs)
        self._buffer: str = ""
        self._dirty: bool = False
        self._timer = None

    def on_mount(self) -> None:
        self._timer = self.set_interval(1 / 30, self._flush)

    def _flush(self) -> None:
        if not self._dirty:
            return
        self._dirty = False
        self.update(f"[bold green]Cody[/bold green]\n{self._buffer}")
        try:
            self.parent.scroll_end(animate=False)
        except Exception:
            pass

    def append(self, text: str) -> None:
        self._buffer += text
        self._dirty = True

    @property
    def full_text(self) -> str:
        return self._buffer

    def on_unmount(self) -> None:
        if self._timer:
            self._timer.stop()


class StatusLine(Static):
    """Bottom status line showing session/model info."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(" Loading...", *args, **kwargs)

    def on_mount(self) -> None:
        self.styles.dock = "bottom"
        self.styles.height = 1
        self.styles.width = "100%"
        self.styles.background = "#003366"
        self.styles.color = "#ffffff"
        self.styles.padding = (0, 2)
