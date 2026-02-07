"""Tool execution with permission flow and multi-round processing.

Handles the agentic loop: model response -> parse tool calls -> check
permission -> execute -> inject results -> call model again -> repeat until
the model produces a response with no tool calls or the round limit is hit.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from app.cli.output import console, print_error, print_warning
from app.cli.tools import (
    PermissionLevel,
    ToolRegistry,
    ToolResult,
    format_tool_result,
    parse_tool_calls,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_MAX_ROUNDS = 5


# ---------------------------------------------------------------------------
# ToolExecutor
# ---------------------------------------------------------------------------


class ToolExecutor:
    """Manages tool execution with permission prompts and multi-round loops.

    Parameters
    ----------
    registry:
        The ``ToolRegistry`` that maps tool names to ``Tool`` instances.
    yolo_mode:
        When ``True`` every tool runs without asking, regardless of its
        declared ``PermissionLevel``.
    max_rounds:
        Safety cap on how many tool-use round-trips are allowed per
        single user turn.
    cwd:
        Working directory passed to every tool invocation.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        yolo_mode: bool = False,
        max_rounds: int = _DEFAULT_MAX_ROUNDS,
        cwd: Path | None = None,
    ) -> None:
        self._registry = registry
        self._yolo_mode = yolo_mode
        self._max_rounds = max_rounds
        self._cwd = cwd or Path.cwd()

    # -- properties ---------------------------------------------------------

    @property
    def yolo_mode(self) -> bool:
        """Whether tools execute without user confirmation."""
        return self._yolo_mode

    @yolo_mode.setter
    def yolo_mode(self, value: bool) -> None:
        self._yolo_mode = value

    @property
    def cwd(self) -> Path:
        """Current working directory for tool execution."""
        return self._cwd

    @cwd.setter
    def cwd(self, value: Path) -> None:
        self._cwd = value

    # -- main loop ----------------------------------------------------------

    async def process_response(
        self,
        response_text: str,
        stream_fn: Callable,
        messages: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, str]]]:
        """Process a model response, executing any embedded tool calls.

        Parameters
        ----------
        response_text:
            The latest assistant message (may contain ``<tool_call>`` blocks).
        stream_fn:
            An async callable with signature
            ``(messages) -> (text, input_tokens, output_tokens)``
            used to call the model for follow-up rounds.
        messages:
            The conversation history so far.  **Mutated in place** -- tool
            results and follow-up assistant messages are appended.

        Returns
        -------
        tuple[str, list[dict[str, str]]]
            ``(final_response_text, updated_messages)`` where the final text
            is the model's last reply that contained no tool calls.
        """
        current_text = response_text
        round_count = 0

        while round_count < self._max_rounds:
            tool_calls = parse_tool_calls(current_text)
            if not tool_calls:
                break

            round_count += 1
            console.print(
                f"\n[muted]  Tool round {round_count}/{self._max_rounds} "
                f"({len(tool_calls)} call{'s' if len(tool_calls) != 1 else ''})[/]"
            )

            results: list[str] = []
            for call in tool_calls:
                result_str = await self._handle_single_call(call)
                results.append(result_str)

            # Inject the assistant message and aggregated results into history
            results_text = "\n\n".join(results)
            messages.append({"role": "assistant", "content": current_text})
            messages.append({"role": "user", "content": results_text})

            # Call the model again so it can react to the tool output
            current_text, _, _ = await stream_fn(messages)

        if round_count >= self._max_rounds:
            print_warning(
                f"Tool loop hit the {self._max_rounds}-round limit",
                detail="The model may still want to use tools. "
                "Increase max_rounds or continue the conversation.",
            )

        return current_text, messages

    # -- single-call handler ------------------------------------------------

    async def _handle_single_call(self, call: dict) -> str:
        """Parse, permission-check, execute, and format one tool call."""
        tool_name: str = call.get("tool", "")
        arguments: dict = call.get("arguments", {})

        # Lookup
        tool = self._registry.get(tool_name)
        if tool is None:
            print_error(f"Unknown tool: {tool_name}")
            return format_tool_result(
                tool_name,
                ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown tool: {tool_name}",
                ),
            )

        # Permission gate
        if not self._check_permission(tool, arguments):
            console.print(f"[muted]  Skipped {tool_name}[/]")
            return format_tool_result(
                tool_name,
                ToolResult(
                    success=False,
                    output="",
                    error=f"Tool '{tool_name}' was denied by the user",
                ),
            )

        # Execute
        try:
            result = await tool.execute(arguments, self._cwd)
        except Exception as exc:  # noqa: BLE001
            print_error(f"Tool '{tool_name}' raised an exception: {exc}")
            return format_tool_result(
                tool_name,
                ToolResult(success=False, output="", error=str(exc)),
            )

        # Display outcome
        if result.success:
            console.print(f"  [cyan]{tool_name}[/] [green]succeeded[/]")
            if result.output:
                lines = result.output.split("\n")
                preview = "\n".join(lines[:5])
                if len(lines) > 5:
                    preview += "\n  ..."
                console.print(f"[muted]{preview}[/]")
        else:
            console.print(f"  [cyan]{tool_name}[/] [red]failed[/]")
            error_preview = (result.error or "Unknown error")[:200]
            if len(result.error or "") > 200:
                error_preview += "..."
            console.print(f"  [red]{error_preview}[/]")

        return format_tool_result(tool_name, result)

    # -- permission ---------------------------------------------------------

    def _check_permission(self, tool, arguments: dict) -> bool:
        """Determine whether a tool invocation is allowed.

        * ``DENY`` -- always blocked.
        * ``AUTO`` or yolo mode on -- always allowed.
        * ``ASK`` -- prompt the user interactively with a rich display.
        """
        if tool.permission == PermissionLevel.DENY:
            print_error(
                f"Tool '{tool.name}' is denied",
                detail="This tool is not allowed to execute.",
            )
            return False

        if tool.permission == PermissionLevel.AUTO or self._yolo_mode:
            return True

        # ASK mode -- show what will run and ask for confirmation
        console.print()

        label = Text()
        label.append("Tool call: ", style="bold yellow")
        label.append(tool.name, style="bold cyan")
        console.print(label)

        # Show arguments as pretty-printed JSON in a panel
        try:
            formatted_args = json.dumps(arguments, indent=2)
        except (TypeError, ValueError):
            formatted_args = str(arguments)

        console.print(Panel(
            Syntax(formatted_args, "json", theme="monokai", line_numbers=False),
            title="[muted]arguments[/]",
            border_style="dim",
            expand=False,
            padding=(0, 1),
        ))

        try:
            answer = input("  Allow? [y/N] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            console.print("[muted]  Denied (interrupted)[/]")
            return False

        return answer in ("y", "yes")

    # -- system prompt fragment ---------------------------------------------

    def get_tool_system_prompt(self) -> str:
        """Return a system-prompt fragment describing available tools.

        Append this to the model's system prompt so it knows what tools
        exist, how to invoke them, and the expected XML format.
        """
        tools_desc = self._registry.tool_descriptions()
        return (
            "\n\nYou have access to the following tools. "
            "To use a tool, output a tool_call block:\n"
            "<tool_call>\n"
            '{"tool": "tool_name", "arguments": {"arg1": "value1"}}\n'
            "</tool_call>\n\n"
            f"{tools_desc}\n\n"
            "After a tool executes, you will receive the result in a "
            "<tool_result> block. You can then use additional tools or "
            "provide your final response. "
            "Only use tools when the user's request requires file "
            "operations or command execution."
        )
