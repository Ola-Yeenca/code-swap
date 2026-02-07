"""Terminal output module for the code-swap CLI.

Provides a modern, Rich-powered display layer with streaming support,
markdown rendering, token/cost tracking, and structured error display.

All terminal output flows through this module. Other modules should import
``console`` and the helper functions rather than printing directly.

Design philosophy: minimal chrome, inline shell feel, Claude Code-inspired.
Devs want tight feedback loops and zero visual noise — not ASCII art banners.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text
from rich.theme import Theme

# ---------------------------------------------------------------------------
# Theme — muted palette, information density over decoration
# ---------------------------------------------------------------------------

_theme = Theme(
    {
        "info": "cyan",
        "info.dim": "dim cyan",
        "success": "bold green",
        "error": "bold red",
        "error.detail": "red",
        "warning": "bold yellow",
        "muted": "dim",
        "accent": "bold white",
        "cost": "green",
        "model": "bold cyan",
        "stat": "dim",
        "prompt.char": "bold green",
        "prompt.model": "cyan",
        "separator": "dim",
    }
)

console = Console(theme=_theme, highlight=False)

# ---------------------------------------------------------------------------
# Version constant (single source of truth for the CLI banner)
# ---------------------------------------------------------------------------

VERSION = "0.4.0"

# ---------------------------------------------------------------------------
# Results directory
# ---------------------------------------------------------------------------

RESULTS_DIR = Path("results")

# ---------------------------------------------------------------------------
# Banner — 4 lines max. Inline feel, not a splash screen.
# ---------------------------------------------------------------------------


def print_banner(model: str = "", key_set: bool = False) -> None:
    """Print a minimal startup banner.

    Design: 4 lines max.  Shows the value prop (one key, all models)
    and current state.  Does NOT take over the viewport.
    """
    key_dot = "[success]\u25cf[/]" if key_set else "[error]\u25cb[/]"
    short = model.split("/", 1)[-1] if "/" in model else model

    console.print()
    console.print(
        f"  [accent]code-swap[/] [muted]v{VERSION}[/]"
        f"  [muted]\u2500[/]  "
        f"[muted]one key, every model[/]  [muted]\u2500[/]  "
        f"[muted]openrouter.ai[/]"
    )
    if model:
        console.print(
            f"  [prompt.model]{short}[/]  {key_dot}"
            f"  [muted]/help  /compare  /model[/]"
        )
    console.print()


# ---------------------------------------------------------------------------
# Response header / footer
# ---------------------------------------------------------------------------


def print_response_header(model: str) -> None:
    """Print a model indicator before the response body."""
    console.print(f"[model]* {model}[/]")
    console.print()


def print_response_footer(
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost: float = 0.0,
    elapsed: float = 0.0,
) -> None:
    """Print token stats and timing after a response."""
    parts: list[str] = []

    if input_tokens:
        parts.append(f"\u25b2 {input_tokens:,}")
    if output_tokens:
        parts.append(f"\u25bc {output_tokens:,}")
    if cost > 0:
        parts.append(f"[cost]${cost:.4f}[/]")
    if elapsed > 0:
        parts.append(f"{elapsed:.1f}s")

    console.print()
    if parts:
        console.print(f"[stat]{_SEP.join(parts)}[/]")
    console.print()


_SEP = "  "


# ---------------------------------------------------------------------------
# Streaming display
# ---------------------------------------------------------------------------


class StreamingDisplay:
    """Accumulates streaming tokens and renders the final result as Markdown.

    A spinner shows "Thinking..." until the first token arrives.
    Raw tokens stream directly for minimum latency.
    On finish, raw text is erased and re-rendered as Rich Markdown.
    """

    def __init__(self, target_console: Console | None = None) -> None:
        self._console = target_console or console
        self._buffer: list[str] = []
        self._start: float = 0.0
        self._lines_written: int = 0
        self._live: Live | None = None
        self._spinner_active: bool = False

    # -- public API ---------------------------------------------------------

    def start(self) -> None:
        """Mark the beginning of a streaming response and show spinner."""
        self._buffer.clear()
        self._lines_written = 0
        self._start = time.monotonic()

        spinner = Spinner("dots", text="[muted]Thinking...[/]", style="info")
        self._live = Live(spinner, console=self._console, transient=True)
        self._live.start()
        self._spinner_active = True

    def token(self, text: str) -> None:
        """Append a single token to the stream and print it raw."""
        if self._spinner_active:
            self._stop_spinner()

        self._buffer.append(text)
        sys.stdout.write(text)
        sys.stdout.flush()
        self._lines_written += text.count("\n")

    def finish(self) -> None:
        """Replace the raw streamed text with a formatted Markdown render."""
        if self._spinner_active:
            self._stop_spinner()

        raw = self.text
        if not raw.strip():
            sys.stdout.write("\n")
            sys.stdout.flush()
            return

        self._erase_streamed_output(raw)
        self._console.print(Markdown(raw))

    @property
    def text(self) -> str:
        """Return the full accumulated response text."""
        return "".join(self._buffer)

    @property
    def elapsed(self) -> float:
        """Seconds elapsed since ``start()`` was called."""
        if self._start == 0.0:
            return 0.0
        return time.monotonic() - self._start

    # -- internals ----------------------------------------------------------

    def _stop_spinner(self) -> None:
        """Stop the Live spinner (safe to call multiple times)."""
        if self._live is not None:
            self._live.stop()
            self._live = None
        self._spinner_active = False

    def _erase_streamed_output(self, raw: str) -> None:
        """Move the cursor up and clear the lines occupied by the raw stream."""
        if not sys.stdout.isatty():
            sys.stdout.write("\n")
            sys.stdout.flush()
            return

        try:
            term_width = self._console.width or 80
        except Exception:
            term_width = 80

        line_count = 0
        for line in raw.split("\n"):
            line_count += max(1, -(-len(line) // term_width))

        sys.stdout.write(f"\r\033[{line_count}A\033[J")
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# Side-by-side panels (compare mode)
# ---------------------------------------------------------------------------


def print_side_by_side(
    left_title: str,
    left_text: str,
    right_title: str,
    right_text: str,
) -> None:
    """Render two responses as side-by-side Rich panels."""
    left_body: Markdown | Text = (
        Markdown(left_text) if left_text.strip() else Text("[no response]", style="muted")
    )
    right_body: Markdown | Text = (
        Markdown(right_text) if right_text.strip() else Text("[no response]", style="muted")
    )

    left_panel = Panel(
        left_body,
        title=f"[model]{left_title}[/]",
        border_style="cyan",
        expand=True,
        padding=(1, 2),
    )
    right_panel = Panel(
        right_body,
        title=f"[model]{right_title}[/]",
        border_style="cyan",
        expand=True,
        padding=(1, 2),
    )

    console.print()
    console.print(Columns([left_panel, right_panel], equal=True, expand=True))


# ---------------------------------------------------------------------------
# Errors, warnings, success, info
# ---------------------------------------------------------------------------


def print_error(
    title: str,
    detail: str | None = None,
    suggestion: str | None = None,
) -> None:
    """Print a structured, actionable error message."""
    console.print(f"[error]\u2718 {title}[/]")
    if detail:
        console.print(f"  [error.detail]{detail}[/]")
    if suggestion:
        console.print(f"  [muted]\u2192 {suggestion}[/]")


def print_warning(
    title: str,
    detail: str | None = None,
) -> None:
    """Print a warning message."""
    console.print(f"[warning]\u26a0 {title}[/]")
    if detail:
        console.print(f"  [muted]{detail}[/]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[success]{message}[/]")


def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[info]{message}[/]")


# ---------------------------------------------------------------------------
# File persistence
# ---------------------------------------------------------------------------


def save_result(label: str, content: str) -> Path:
    """Save output to ``results/`` with a timestamp. Returns the file path."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = RESULTS_DIR / f"{ts}_{label}.md"
    path.write_text(content, encoding="utf-8")
    return path


def print_saved(path: Path) -> None:
    """Show where a result was saved."""
    console.print(f"[muted]Saved to {path}[/]")
