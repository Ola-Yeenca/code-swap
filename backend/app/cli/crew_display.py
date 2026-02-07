"""Rich terminal display for multi-model crew execution.

Renders a live-updating dashboard:
- Crew header with agent count and task
- Agent status table (name, model, status, one-line summary)
- Active agent streaming section
- Budget/time footer
- Summary table on completion
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass, field

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from app.cli.output import console


# ---------------------------------------------------------------------------
# Agent state tracking
# ---------------------------------------------------------------------------


@dataclass
class AgentState:
    """Mutable state for a single agent during a crew run."""

    name: str
    model: str
    status: str = "pending"
    summary: str = ""
    output: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0


# ---------------------------------------------------------------------------
# Live display
# ---------------------------------------------------------------------------


class CrewDisplay:
    """Live terminal display for crew execution.

    Consumes events from an ``asyncio.Queue`` pushed by the crew engine
    and renders a Rich Live dashboard that updates in real time.

    Event types handled:
        crew_start, plan, agent_start, agent_delta, agent_done,
        synthesis_delta, crew_done, error
    """

    def __init__(self, crew_name: str, task: str, budget: float = 5.0) -> None:
        self._crew_name = crew_name
        self._task = task
        self._budget = budget
        self._agents: dict[str, AgentState] = {}
        self._active_agent: str | None = None
        self._synthesis_text: str = ""
        self._start_time = time.monotonic()
        self._total_cost: float = 0.0
        self._status: str = "starting"
        self._subtask_count: int = 0

    # -- public API ---------------------------------------------------------

    async def run(self, event_queue: asyncio.Queue) -> None:
        """Consume events from *event_queue* and render live display.

        Blocks until a ``crew_done`` or ``error`` event is received.
        """
        with Live(
            self._render(),
            console=console,
            refresh_per_second=8,
            transient=False,
        ) as live:
            while True:
                try:
                    event = await asyncio.wait_for(
                        event_queue.get(), timeout=0.2
                    )
                except asyncio.TimeoutError:
                    # Re-render on timeout to keep spinner / elapsed ticking
                    live.update(self._render())
                    continue

                self._handle_event(event)
                live.update(self._render())

                if event.get("type") in ("crew_done", "error"):
                    break

        # Print final summary outside the Live context
        self._print_summary()

    # -- event handling -----------------------------------------------------

    def _handle_event(self, event: dict) -> None:
        """Process a single event and update internal state."""
        etype = event.get("type", "")

        if etype == "crew_start":
            self._status = "planning"
            for name in event.get("agents", []):
                self._agents[name] = AgentState(name=name, model="")

        elif etype == "plan":
            self._status = "executing"
            subtasks = event.get("subtasks", [])
            self._subtask_count = len(subtasks)
            for st in subtasks:
                agent_name = st.get("assignTo", "")
                if agent_name in self._agents:
                    self._agents[agent_name].summary = st.get(
                        "description", ""
                    )[:60]

        elif etype == "agent_start":
            name = event.get("agent", "")
            if name in self._agents:
                self._agents[name].status = "running"
                self._agents[name].model = event.get("model", "")
                self._active_agent = name

        elif etype == "agent_delta":
            name = event.get("agent", "")
            text = event.get("text", "")
            if name in self._agents:
                self._agents[name].output += text
                self._active_agent = name

        elif etype == "agent_done":
            name = event.get("agent", "")
            if name in self._agents:
                agent = self._agents[name]
                agent.status = "done"
                agent.tokens_in = event.get("tokens_in", 0)
                agent.tokens_out = event.get("tokens_out", 0)
                agent.cost = event.get("cost", 0.0)
                # Update summary to first meaningful line of output
                first_line = agent.output.split("\n")[0][:60]
                if first_line:
                    agent.summary = first_line
                # Move active to next running agent
                running = [
                    n
                    for n, a in self._agents.items()
                    if a.status == "running"
                ]
                self._active_agent = running[0] if running else None

        elif etype == "synthesis_delta":
            self._status = "synthesizing"
            self._synthesis_text += event.get("text", "")
            self._active_agent = None

        elif etype == "crew_done":
            self._status = "done"
            self._total_cost = event.get("totalCost", 0.0)

        elif etype == "error":
            self._status = "error"

    # -- rendering ----------------------------------------------------------

    def _render(self) -> Panel:
        """Build the full display panel."""
        elapsed = time.monotonic() - self._start_time
        elapsed_str = f"{int(elapsed // 60)}:{int(elapsed % 60):02d}"

        # Header
        agent_count = len(self._agents)
        header = Text.assemble(
            (" CREW: ", "bold cyan"),
            (self._crew_name, "bold white"),
            (f" ({agent_count} agents)", "dim"),
            ("  Task: ", "dim"),
            (self._task[:50], "white"),
        )

        # Agent status table
        table = Table(
            show_header=True,
            header_style="dim",
            box=None,
            padding=(0, 2),
        )
        table.add_column("Agent", style="cyan", min_width=14)
        table.add_column("Status", min_width=10)
        table.add_column("Summary", style="dim")

        status_styles = {
            "pending": "[dim]pending[/]",
            "running": "[bold blue]running[/]",
            "done": "[green]done[/]",
            "failed": "[red]failed[/]",
        }

        for name, agent in self._agents.items():
            status_display = status_styles.get(agent.status, agent.status)
            summary = (
                agent.summary[:50] + "..."
                if len(agent.summary) > 50
                else agent.summary
            )
            table.add_row(name, status_display, summary)

        # Assemble parts
        parts: list = [header, Text(""), table, Text("")]

        if self._active_agent and self._active_agent in self._agents:
            agent = self._agents[self._active_agent]
            active_header = Text.assemble(
                ("  ACTIVE: ", "bold"),
                (self._active_agent, "cyan"),
                (f" ({agent.model})", "dim"),
            )
            parts.append(active_header)
            parts.append(Text(""))
            # Show last 10 lines of output
            output_lines = agent.output.split("\n")
            visible = "\n".join(output_lines[-10:])
            parts.append(Text(visible, style="white"))
        elif self._synthesis_text:
            parts.append(Text("  SYNTHESIS:", style="bold"))
            parts.append(Text(""))
            synth_lines = self._synthesis_text.split("\n")
            visible = "\n".join(synth_lines[-10:])
            parts.append(Text(visible, style="white"))
        elif self._status == "planning":
            parts.append(
                Spinner("dots", text=" Planning subtasks...", style="cyan")
            )

        # Footer
        parts.append(Text(""))
        footer = Text.assemble(
            ("  Budget: ", "dim"),
            (f"${self._total_cost:.4f}", "green"),
            (f" / ${self._budget:.2f}", "dim"),
            ("  |  ", "dim"),
            (f"{self._subtask_count} subtasks", "dim"),
            ("  |  ", "dim"),
            (elapsed_str, "dim"),
        )
        parts.append(footer)

        border = "cyan" if self._status != "error" else "red"
        return Panel(
            Group(*parts),
            border_style=border,
            padding=(1, 2),
        )

    # -- final summary ------------------------------------------------------

    def _print_summary(self) -> None:
        """Print final summary table after crew completion."""
        console.print()

        title = (
            "Crew Run Complete"
            if self._status == "done"
            else "Crew Run Failed"
        )
        title_style = (
            "bold green" if self._status == "done" else "bold red"
        )

        table = Table(
            title=title,
            title_style=title_style,
            show_lines=False,
            border_style="dim",
            header_style="bold dim",
        )
        table.add_column("Agent", style="cyan", min_width=14)
        table.add_column("Model", style="dim", min_width=20)
        table.add_column("Tokens", justify="right", min_width=10)
        table.add_column("Cost", justify="right", style="green", min_width=10)

        total_tokens = 0
        for name, agent in self._agents.items():
            tokens = agent.tokens_in + agent.tokens_out
            total_tokens += tokens
            table.add_row(
                name,
                agent.model,
                f"{tokens:,}",
                f"${agent.cost:.4f}",
            )

        table.add_section()
        table.add_row(
            "[bold]TOTAL[/]",
            "",
            f"[bold]{total_tokens:,}[/]",
            f"[bold green]${self._total_cost:.4f}[/]",
        )

        console.print(table)
        console.print()

        # Print synthesis as rendered markdown
        if self._synthesis_text:
            console.print("[bold]Final Result:[/]")
            console.print()
            console.print(Markdown(self._synthesis_text))
            console.print()
