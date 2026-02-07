"""Compare mode: tab toggle and split pane views for the code-swap CLI.

Provides two display modes for comparing model responses:

- **TabCompare**: Interactive tab toggle between two responses. The user
  presses ``a``/``b`` to switch tabs and ``q`` or Enter to close.
- **split_pane**: Static side-by-side render using ``rich.layout.Layout``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from rich.console import Console
from rich.layout import Layout
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text


# ---------------------------------------------------------------------------
# Data container for compare results
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class CompareResult:
    """Stores the output of a comparison for later replay."""

    prompt: str
    model_a: str
    text_a: str
    model_b: str
    text_b: str


# ---------------------------------------------------------------------------
# Tab toggle view
# ---------------------------------------------------------------------------

class TabCompare:
    """Interactive tab toggle between two model responses.

    Shows a header with two tab labels.  The active tab is bold and
    highlighted.  The user presses ``a``/``b`` to switch and ``q`` or
    Enter to close.

    Parameters
    ----------
    result:
        A :class:`CompareResult` containing both responses.
    target_console:
        Optional Rich console (defaults to the module-level console).
    """

    def __init__(
        self,
        result: CompareResult,
        target_console: Console | None = None,
    ) -> None:
        self._result = result
        self._console = target_console or _get_console()
        self._active: str = "a"  # "a" or "b"

    def show(self) -> None:
        """Run the interactive tab-toggle loop."""
        while True:
            self._render()
            key = self._read_key()
            if key in ("q", "\r", "\n"):
                break
            if key == "a":
                self._active = "a"
            elif key == "b":
                self._active = "b"

    # -- rendering ----------------------------------------------------------

    def _render(self) -> None:
        """Clear and redraw the header + active panel."""
        # Clear screen
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

        r = self._result

        # Tab header
        if self._active == "a":
            header = Text.assemble(
                (" [", "separator"),
                (f" {_short(r.model_a)} ", "black on #458af7"),
                ("] ", "separator"),
                ("  ", ""),
                (" ", "muted"),
                (f" {_short(r.model_b)} ", "muted"),
                (" ", "muted"),
            )
        else:
            header = Text.assemble(
                (" ", "muted"),
                (f" {_short(r.model_a)} ", "muted"),
                (" ", "muted"),
                ("  ", ""),
                (" [", "separator"),
                (f" {_short(r.model_b)} ", "black on #458af7"),
                ("] ", "separator"),
            )

        self._console.print()
        self._console.print(header)
        self._console.print()

        # Active content panel
        if self._active == "a":
            model, text = r.model_a, r.text_a
        else:
            model, text = r.model_b, r.text_b

        body = Markdown(text) if text.strip() else Text("[no response]", style="muted")
        panel = Panel(
            body,
            title=f"[model]\u25c8 {model}[/]",
            border_style="separator",
            padding=(1, 2),
        )
        self._console.print(panel)

        # Footer hint
        self._console.print(
            "[dim]  a/b switch tabs \u2502 q or Enter to close[/]"
        )

    # -- input --------------------------------------------------------------

    @staticmethod
    def _read_key() -> str:
        """Read a single keypress (Unix only)."""
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        return ch


# ---------------------------------------------------------------------------
# Static split pane
# ---------------------------------------------------------------------------

def split_pane(
    result: CompareResult,
    target_console: Console | None = None,
) -> None:
    """Render both responses side-by-side using ``rich.layout.Layout``."""
    con = target_console or _get_console()

    body_a = Markdown(result.text_a) if result.text_a.strip() else Text("[no response]", style="dim")
    body_b = Markdown(result.text_b) if result.text_b.strip() else Text("[no response]", style="dim")

    panel_a = Panel(
        body_a,
        title=f"[model]\u25c8 {result.model_a}[/]",
        border_style="separator",
        padding=(1, 2),
    )
    panel_b = Panel(
        body_b,
        title=f"[model]\u25c8 {result.model_b}[/]",
        border_style="separator",
        padding=(1, 2),
    )

    layout = Layout()
    layout.split_row(
        Layout(panel_a, name="left"),
        Layout(panel_b, name="right"),
    )

    con.print()
    con.print(layout)
    con.print()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _short(model_id: str) -> str:
    """Return the short name portion of a model ID (after the ``/``)."""
    return model_id.split("/", 1)[-1] if "/" in model_id else model_id


def _get_console() -> Console:
    """Lazily import the shared console to avoid circular imports."""
    from app.cli.output import console as shared_console
    return shared_console
