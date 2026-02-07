"""Interactive REPL for the code-swap CLI.

Provides a persistent, multi-turn chat experience powered by OpenRouter.
Supports slash commands, streaming markdown, model switching, file context
loading, tab-toggle compare, split-pane view, session persistence,
git awareness, tool execution, and multi-model crew orchestration.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from rich.table import Table

from app.cli.config import OPENROUTER_BASE_URL, load_config
from app.cli.conversation import Conversation, TokenTracker
from app.cli.sessions import SessionStore
from app.cli.git_context import (
    detect_git_repo,
    collect_git_info,
    format_git_context,
    collect_repo_summary,
    get_full_diff,
)
from app.cli.tools import ToolRegistry
from app.cli.tool_executor import ToolExecutor
from app.cli.crew import load_crew, list_crews, ensure_default_crews
from app.cli.engine import CrewEngine
from app.cli.crew_display import CrewDisplay
from app.cli.smart_router import SmartRouter

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HISTORY_PATH = Path.home() / ".code_swap_history"

_SLASH_COMMANDS: list[str] = [
    "/model",
    "/compare",
    "/split",
    "/critique",
    "/tokens",
    "/cost",
    "/status",
    "/new",
    "/context",
    "/save",
    "/clear",
    "/help",
    "/quit",
    "/exit",
    # v0.4.0 — sessions
    "/save-session",
    "/load-session",
    "/sessions",
    "/resume",
    "/delete-session",
    # v0.4.0 — git
    "/git",
    "/diff",
    "/repo",
    # v0.4.0 — tools
    "/tools",
    "/yolo",
    # v0.4.0 — crews
    "/crew",
    "/run",
    "/agents",
    # v0.5.0 — smart routing
    "/auto",
    "/route",
]

# Regex to detect @file references in user input.
_FILE_REF_RE = re.compile(r"@([\w./_~-]+)")

# Context window size assumed for percentage calculation (128k default).
_ASSUMED_CONTEXT_WINDOW = 128_000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear_screen() -> None:
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def _short_model_name(model_id: str) -> str:
    """Return the short name after the ``/`` in a model ID."""
    return model_id.split("/", 1)[-1] if "/" in model_id else model_id


def _format_duration(seconds: float) -> str:
    """Format seconds as ``M:SS``."""
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


async def _stream_openrouter(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
) -> AsyncGenerator[str, None]:
    """Stream tokens from OpenRouter's chat/completions endpoint."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/code-swap",
        "X-Title": "code-swap",
    }
    body = {
        "model": model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=body,
        ) as response:
            if response.status_code >= 400:
                await response.aread()
                response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[len("data:"):].strip()
                if payload == "[DONE]":
                    break
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                choices = event.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    text = delta.get("content")
                    if text:
                        yield text

                usage = event.get("usage")
                if usage:
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    yield f"__usage__:{prompt_tokens}:{completion_tokens}"


async def _collect_openrouter(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
) -> str:
    """Run a prompt and collect the full response without streaming."""
    full = []
    async for token in _stream_openrouter(api_key, model, messages):
        if not token.startswith("__usage__:"):
            full.append(token)
    return "".join(full)


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------

class Repl:
    """Interactive REPL for code-swap."""

    def __init__(
        self,
        api_key: str,
        default_model: str,
        output: Any,  # noqa: ANN401
        yolo_mode: bool = False,
    ) -> None:
        self._api_key = api_key
        self._model: str = default_model
        self._out = output
        self._conversation = Conversation()
        self._auto_save: bool = True
        self._session_start: float = 0.0
        self._last_interrupt: float = 0.0
        self._last_compare: Any = None  # CompareResult or None

        # v0.4.0 — sessions
        self._session_store = SessionStore()
        self._session_id: str | None = None

        # v0.4.0 — git
        self._git_root: Path | None = None
        self._git_info: Any = None  # GitInfo or None

        # v0.4.0 — tools
        self._registry = ToolRegistry()
        self._tool_executor = ToolExecutor(
            registry=self._registry,
            yolo_mode=yolo_mode,
        )

        # v0.4.0 — crews
        self._active_crew_name: str | None = None
        self._active_crew_config: Any = None  # CrewConfig or None

        # v0.5.0 — smart routing
        cfg = load_config()
        self._auto_route: bool = cfg.auto_route
        self._router = SmartRouter(
            default_model=default_model,
            route_overrides=cfg.route_overrides,
        )

        self._session: PromptSession[str] = PromptSession(
            history=FileHistory(str(_HISTORY_PATH)),
            auto_suggest=AutoSuggestFromHistory(),
            completer=WordCompleter(_SLASH_COMMANDS, sentence=True),
            complete_while_typing=True,
            enable_history_search=True,
        )

    # -- Properties ----------------------------------------------------------

    @property
    def model(self) -> str:
        return self._model

    @property
    def tracker(self) -> TokenTracker:
        return self._conversation.tracker

    # -- Toolbar — information-dense, no jargon ------------------------------

    def _bottom_toolbar(self) -> HTML:
        t = self._conversation.tracker
        save_dot = "\u25cf" if self._auto_save else "\u25cb"
        cost_lbl = f"${t.session_cost:.4f}" if t.request_count else "$0"
        tokens_lbl = f"{t.total_tokens:,}" if t.request_count else "0"

        ctx_tokens = self._conversation.estimated_tokens
        ctx_pct = min(100, int(ctx_tokens / _ASSUMED_CONTEXT_WINDOW * 100))

        elapsed = time.monotonic() - self._session_start if self._session_start else 0
        time_lbl = _format_duration(elapsed)

        # Build optional segments
        extra_parts = ""
        if self._git_info is not None:
            extra_parts += f"  \u2502 \ue0a0 {self._git_info.branch}"
        if self._tool_executor.yolo_mode:
            extra_parts += "  \u2502 [yolo]"
        if self._auto_route:
            extra_parts += "  \u2502 [auto]"

        return HTML(
            f'<style bg="#1a1a2e" fg="#888">'
            f"  {self._model}"
            f"  \u2502 ctx {ctx_pct}%"
            f"  \u2502 {tokens_lbl} tok  {cost_lbl}"
            f"  \u2502 {time_lbl}"
            f"  \u2502 save {save_dot}"
            f"{extra_parts}"
            f"</style>"
        )

    # -- File context --------------------------------------------------------

    def _extract_file_refs(self, text: str) -> tuple[str, list[tuple[str, str]]]:
        """Parse @file references from user input."""
        files: list[tuple[str, str]] = []
        clean = text

        for match in _FILE_REF_RE.finditer(text):
            path_str = match.group(1)
            target = Path(path_str).expanduser().resolve()
            if target.is_file():
                try:
                    content = target.read_text(encoding="utf-8")
                    files.append((str(target), content))
                    clean = clean.replace(match.group(0), "", 1)
                except Exception as exc:  # noqa: BLE001
                    self._out.print_error(f"Cannot read {target}: {exc}")
            else:
                self._out.print_error(
                    f"File not found: {path_str}",
                    suggestion="Use absolute path or path relative to cwd",
                )

        return clean.strip(), files

    # -- Git context helpers -------------------------------------------------

    def _inject_git_context(self) -> None:
        """Collect git info and inject it into the system prompt."""
        if self._git_root is None:
            return
        self._git_info = collect_git_info(self._git_root)
        git_block = format_git_context(self._git_info)

        current_prompt = self._conversation.system_prompt
        # Replace existing git context block if present
        if "<git_context>" in current_prompt and "</git_context>" in current_prompt:
            import re as _re
            current_prompt = _re.sub(
                r"<git_context>.*?</git_context>",
                git_block,
                current_prompt,
                flags=_re.DOTALL,
            )
            self._conversation.set_system_prompt(current_prompt)
        else:
            self._conversation.set_system_prompt(current_prompt + "\n\n" + git_block)

    # -- Session auto-resume -------------------------------------------------

    def _auto_resume_session(self) -> None:
        """Attempt to resume the latest session if auto_resume is enabled."""
        latest = self._session_store.get_latest()
        if latest is None:
            return
        try:
            data = self._session_store.load_session(latest.session_id)
            self._conversation = Conversation.from_serializable({
                "system_prompt": data["system_prompt"],
                "messages": [
                    {"role": m["role"], "content": m["content"]}
                    for m in data["messages"]
                ],
                "tracker_records": [],
            })
            self._model = data["meta"].model
            self._session_id = latest.session_id
            self._out.print_success(
                f"Resumed session: {latest.name} ({latest.message_count} messages)"
            )
        except Exception as exc:  # noqa: BLE001
            self._out.print_error(f"Auto-resume failed: {exc}")

    # -- Slash-command handlers — existing -----------------------------------

    async def _cmd_model(self) -> None:
        """Switch the active model via interactive picker."""
        try:
            from app.cli.picker import fetch_models, pick_model_async

            self._out.console.print("[muted]Fetching models from OpenRouter...[/]")
            models = await fetch_models(self._api_key)
            if not models:
                self._out.print_error("No models returned from OpenRouter")
                return
            chosen = await pick_model_async(models, current_model=self._model)
            if chosen:
                self._model = chosen
                self._out.print_success(f"Switched to {self._model}")
        except (KeyboardInterrupt, EOFError):
            self._out.console.print("[muted]Model switch cancelled.[/]")
        except Exception as exc:  # noqa: BLE001
            self._out.print_error(f"Model picker failed: {exc}")

    async def _cmd_compare(self, prompt: str) -> None:
        """Run a prompt through two models and display as tab toggle."""
        if not prompt.strip():
            self._out.print_error("Usage: /compare <prompt>")
            return

        self._out.console.print(
            f"[muted]Comparing {self._model} with a second model...[/]"
        )
        try:
            from app.cli.picker import fetch_models, pick_model_async

            models = await fetch_models(self._api_key)
            self._out.console.print("[muted]Pick the second model:[/]")
            second_model = await pick_model_async(models, current_model=None)
        except (KeyboardInterrupt, EOFError):
            self._out.console.print("[muted]Compare cancelled.[/]")
            return
        except Exception as exc:  # noqa: BLE001
            self._out.print_error(f"Model picker failed: {exc}")
            return

        messages = [{"role": "user", "content": prompt}]

        self._out.console.print("[muted]Running both models...[/]")

        left, right = await asyncio.gather(
            _collect_openrouter(self._api_key, self._model, messages),
            _collect_openrouter(self._api_key, second_model, messages),
        )

        from app.cli.compare import CompareResult, TabCompare

        result = CompareResult(
            prompt=prompt,
            model_a=self._model,
            text_a=left,
            model_b=second_model,
            text_b=right,
        )
        self._last_compare = result

        TabCompare(result).show()

        if self._auto_save:
            combined = (
                f"# Compare\n\n**Prompt:** {prompt}\n\n"
                f"## {self._model}\n\n{left}\n\n"
                f"## {second_model}\n\n{right}"
            )
            path = self._out.save_result("compare", combined)
            self._out.print_saved(path)

    async def _cmd_split(self, arg: str) -> None:
        """Show last compare result in split pane, or run a new compare."""
        from app.cli.compare import split_pane

        if self._last_compare is not None and not arg.strip():
            split_pane(self._last_compare)
        elif arg.strip():
            await self._cmd_compare(arg)
            if self._last_compare is not None:
                split_pane(self._last_compare)
        else:
            self._out.print_error(
                "No previous compare result",
                suggestion="Run /compare <prompt> first, or /split <prompt>",
            )

    async def _cmd_critique(self, filepath: str) -> None:
        """Read a file and run compare on its contents."""
        filepath = filepath.strip()
        if not filepath:
            self._out.print_error("Usage: /critique <filepath>")
            return

        target = Path(filepath).expanduser().resolve()
        if not target.is_file():
            self._out.print_error(f"File not found: {target}")
            return

        try:
            source = target.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            self._out.print_error(f"Cannot read {target}: {exc}")
            return

        review_prompt = (
            "Analyze this code. Call out key points, potential bugs, "
            "performance issues, and recommendations.\n\n"
            f"```\n{source}\n```"
        )

        await self._cmd_compare(review_prompt)

    async def _cmd_tokens(self) -> None:
        """Display session token usage and cost."""
        t = self._conversation.tracker
        if t.request_count == 0:
            self._out.console.print("[muted]No requests made yet.[/]")
            return
        self._out.console.print(f"[info]{t.format_stats()}[/]")
        self._out.console.print(
            f"[muted]  Context: ~{self._conversation.estimated_tokens:,} tokens "
            f"({self._conversation.message_count} messages)[/]"
        )

    async def _cmd_status(self) -> None:
        """Show a clean status table."""
        t = self._conversation.tracker
        elapsed = time.monotonic() - self._session_start if self._session_start else 0
        ctx_tokens = self._conversation.estimated_tokens
        ctx_pct = min(100, int(ctx_tokens / _ASSUMED_CONTEXT_WINDOW * 100))

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("key", style="muted", min_width=14)
        table.add_column("value", style="info")

        table.add_row("Model", f"[bold cyan]{self._model}[/]")
        table.add_row("Session time", _format_duration(elapsed))
        table.add_row("Requests", str(t.request_count))
        table.add_row("Tokens in", f"{t.session_input_tokens:,}")
        table.add_row("Tokens out", f"{t.session_output_tokens:,}")
        table.add_row("Total tokens", f"{t.total_tokens:,}")
        table.add_row("Cost", f"[green]${t.session_cost:.4f}[/]")
        table.add_row("Context", f"~{ctx_tokens:,} tokens ({ctx_pct}%)")
        table.add_row(
            "Auto-save",
            "[green]on[/]" if self._auto_save else "[red]off[/]",
        )
        # v0.4.0 additions
        if self._git_info is not None:
            modified_count = len(self._git_info.modified_files)
            table.add_row("Git branch", f"[cyan]{self._git_info.branch}[/] ({modified_count} modified)")
        if self._session_id:
            table.add_row("Session ID", f"[dim]{self._session_id[:12]}...[/]")
        table.add_row(
            "Yolo mode",
            "[bold yellow]on[/]" if self._tool_executor.yolo_mode else "[dim]off[/]",
        )
        if self._active_crew_name:
            table.add_row("Active crew", f"[cyan]{self._active_crew_name}[/]")

        self._out.console.print()
        self._out.console.print(table)
        self._out.console.print()

    async def _cmd_new(self) -> None:
        """Start a fresh conversation."""
        self._conversation.clear()
        self._session_id = None
        self._git_info = None
        # Re-inject git context and tool prompt if we have a git root
        if self._git_root:
            self._inject_git_context()
        tool_prompt = self._tool_executor.get_tool_system_prompt()
        current_prompt = self._conversation.system_prompt
        self._conversation.set_system_prompt(current_prompt + tool_prompt)
        self._out.print_success("New conversation started")

    async def _cmd_context(self) -> None:
        """Show conversation context size."""
        self._out.console.print(
            f"[info]Context: ~{self._conversation.estimated_tokens:,} tokens "
            f"({self._conversation.message_count} messages)[/]"
        )

    async def _cmd_help(self) -> None:
        """Show help as a clean table — plain English, no jargon."""
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("command", style="cyan", min_width=28)
        table.add_column("description", style="dim")

        commands = [
            ("/model", "Switch the active model (fuzzy picker)"),
            ("/compare <prompt>", "Run prompt through two models (tab view)"),
            ("/split [prompt]", "Show last compare as split pane"),
            ("/critique <file>", "Analyze a file with two models"),
            ("/tokens, /cost", "Show token usage and cost"),
            ("/status", "Full session status"),
            ("/new", "Start fresh conversation"),
            ("/context", "Show context size"),
            ("/save", "Toggle auto-save"),
            ("/clear", "Clear terminal"),
            ("/help", "This message"),
            ("/quit, /exit", "Exit"),
            # v0.4.0 — sessions
            ("", ""),
            ("/save-session [name]", "Save conversation to a named session"),
            ("/load-session [name|id]", "Load a saved session"),
            ("/sessions", "List all saved sessions"),
            ("/resume", "Resume the most recent session"),
            ("/delete-session [name|id]", "Delete a saved session"),
            # v0.4.0 — git
            ("", ""),
            ("/git", "Refresh git context in system prompt"),
            ("/diff [--staged]", "Load git diff into conversation context"),
            ("/repo", "Show repository structure summary"),
            # v0.4.0 — tools
            ("", ""),
            ("/tools", "List available tools and permissions"),
            ("/yolo", "Toggle auto-approve for tool execution"),
            # v0.4.0 — crews
            ("", ""),
            ("/crew list", "List available crew configurations"),
            ("/crew load <name>", "Load a crew for /run tasks"),
            ("/crew show", "Show agents in the active crew"),
            ("/run <task>", "Execute a task with the active crew"),
            ("/agents", "Show agents in the active crew"),
            # v0.5.0 — smart routing
            ("", ""),
            ("/auto", "Toggle smart routing (auto-picks best model per task)"),
            ("/route [prompt]", "Show route table or test routing for a prompt"),
        ]
        for cmd, desc in commands:
            if cmd == "" and desc == "":
                table.add_row("", "")
            else:
                table.add_row(cmd, desc)

        self._out.console.print()
        self._out.console.print(table)
        self._out.console.print()
        self._out.console.print("[muted]  @filename to include file context. Ctrl+C twice to exit.[/]")
        self._out.console.print()

    async def _cmd_clear(self) -> None:
        _clear_screen()

    async def _cmd_save(self) -> None:
        self._auto_save = not self._auto_save
        state = "[bold green]on[/]" if self._auto_save else "[bold red]off[/]"
        self._out.console.print(f"Auto-save is now {state}")

    # -- Slash-command handlers — v0.4.0 sessions ----------------------------

    async def _cmd_save_session(self, name: str) -> None:
        """Save the current conversation as a named session."""
        if self._conversation.message_count == 0:
            self._out.print_error("Nothing to save — conversation is empty")
            return
        session_name = name.strip() if name.strip() else None
        try:
            sid = self._session_store.save_session(
                self._conversation,
                self._model,
                session_name,
            )
            self._session_id = sid
            display_name = session_name or "(auto-named)"
            self._out.print_success(f"Session saved: {display_name} [{sid[:12]}]")
        except Exception as exc:  # noqa: BLE001
            self._out.print_error(f"Failed to save session: {exc}")

    async def _cmd_load_session(self, arg: str) -> None:
        """Load a session by name or ID."""
        arg = arg.strip()

        if not arg:
            # Interactive selection: list sessions and let user pick
            sessions = self._session_store.list_sessions()
            if not sessions:
                self._out.console.print("[muted]No saved sessions.[/]")
                return
            self._out.console.print()
            for i, s in enumerate(sessions[:20], 1):
                self._out.console.print(
                    f"  [cyan]{i:>3}[/]  {s.name}  "
                    f"[dim]({s.message_count} msgs, {s.model})[/]"
                )
            self._out.console.print()
            try:
                choice = input("  Pick a number (or Enter to cancel): ").strip()
            except (KeyboardInterrupt, EOFError):
                self._out.console.print("[muted]Cancelled.[/]")
                return
            if not choice:
                return
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(sessions[:20]):
                    arg = sessions[idx].session_id
                else:
                    self._out.print_error("Invalid selection")
                    return
            except ValueError:
                self._out.print_error("Invalid number")
                return

        # Try to find by name prefix first, then by ID
        session_id = self._resolve_session(arg)
        if session_id is None:
            self._out.print_error(
                f"Session not found: {arg}",
                suggestion="Use /sessions to list available sessions",
            )
            return

        try:
            data = self._session_store.load_session(session_id)
        except (FileNotFoundError, ValueError) as exc:
            self._out.print_error(f"Failed to load session: {exc}")
            return

        # Reconstruct conversation
        self._conversation = Conversation.from_serializable({
            "system_prompt": data["system_prompt"],
            "messages": [
                {"role": m["role"], "content": m["content"]}
                for m in data["messages"]
            ],
            "tracker_records": [],
        })
        self._model = data["meta"].model
        self._session_id = session_id
        msg_count = len(data["messages"])
        self._out.print_success(
            f"Loaded session: {data['meta'].name} ({msg_count} messages, model: {self._model})"
        )

    async def _cmd_sessions(self) -> None:
        """List all saved sessions as a Rich table."""
        sessions = self._session_store.list_sessions()
        if not sessions:
            self._out.console.print("[muted]No saved sessions.[/]")
            return

        table = Table(
            title="Saved Sessions",
            show_lines=False,
            border_style="dim",
            title_style="bold",
            header_style="bold dim",
        )
        table.add_column("Name", style="cyan", min_width=20)
        table.add_column("Model", style="dim", min_width=20)
        table.add_column("Messages", justify="right", min_width=8)
        table.add_column("Tokens", justify="right", min_width=10)
        table.add_column("Cost", justify="right", style="green", min_width=8)
        table.add_column("Updated", style="dim", min_width=16)

        for s in sessions:
            # Shorten the timestamp for display
            updated = s.updated_at[:16].replace("T", " ") if s.updated_at else ""
            table.add_row(
                s.name,
                _short_model_name(s.model),
                str(s.message_count),
                f"{s.total_tokens:,}",
                f"${s.total_cost:.4f}",
                updated,
            )

        self._out.console.print()
        self._out.console.print(table)
        self._out.console.print(f"\n[muted]{len(sessions)} session(s)[/]")
        self._out.console.print()

    async def _cmd_resume(self) -> None:
        """Resume the most recent session."""
        latest = self._session_store.get_latest()
        if latest is None:
            self._out.console.print("[muted]No saved sessions to resume.[/]")
            return
        await self._cmd_load_session(latest.session_id)

    async def _cmd_delete_session(self, arg: str) -> None:
        """Delete a saved session."""
        arg = arg.strip()
        if not arg:
            self._out.print_error(
                "Usage: /delete-session <name or id>",
                suggestion="Use /sessions to list available sessions",
            )
            return

        session_id = self._resolve_session(arg)
        if session_id is None:
            self._out.print_error(f"Session not found: {arg}")
            return

        # Confirm deletion
        try:
            answer = input(f"  Delete session {session_id[:12]}...? [y/N] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            self._out.console.print("[muted]Cancelled.[/]")
            return

        if answer not in ("y", "yes"):
            self._out.console.print("[muted]Cancelled.[/]")
            return

        deleted = self._session_store.delete_session(session_id)
        if deleted:
            if self._session_id == session_id:
                self._session_id = None
            self._out.print_success("Session deleted")
        else:
            self._out.print_error("Failed to delete session")

    def _resolve_session(self, arg: str) -> str | None:
        """Resolve a session name or ID to a session_id string."""
        sessions = self._session_store.list_sessions()
        # Try name prefix match
        for s in sessions:
            if s.name.lower().startswith(arg.lower()):
                return s.session_id
        # Try ID prefix match
        for s in sessions:
            if s.session_id.startswith(arg):
                return s.session_id
        return None

    # -- Slash-command handlers — v0.4.0 git ---------------------------------

    async def _cmd_git(self) -> None:
        """Refresh git context and re-inject into system prompt."""
        if self._git_root is None:
            self._git_root = detect_git_repo()
        if self._git_root is None:
            self._out.console.print("[muted]Not in a git repository.[/]")
            return
        self._inject_git_context()
        modified_count = len(self._git_info.modified_files) if self._git_info else 0
        branch = self._git_info.branch if self._git_info else "unknown"
        self._out.print_success(f"Git context refreshed: {branch} ({modified_count} modified)")

    async def _cmd_diff(self, arg: str) -> None:
        """Load git diff into conversation context."""
        if self._git_root is None:
            self._out.console.print("[muted]Not in a git repository.[/]")
            return

        staged_only = "--staged" in arg
        diff_text = get_full_diff(self._git_root, staged_only=staged_only)
        if not diff_text.strip():
            label = "staged changes" if staged_only else "changes"
            self._out.console.print(f"[muted]No {label} detected.[/]")
            return

        line_count = diff_text.count("\n")
        wrapped = f"<git_diff>\n{diff_text}\n</git_diff>"
        self._conversation.add_user_message(wrapped)
        kind = "staged diff" if staged_only else "diff"
        self._out.print_success(f"Loaded {kind} ({line_count} lines) into context")

    async def _cmd_repo(self) -> None:
        """Show repository structure summary."""
        if self._git_root is None:
            self._out.console.print("[muted]Not in a git repository.[/]")
            return

        summary = collect_repo_summary(self._git_root)

        table = Table(
            title=f"Repository: {summary.root.name}",
            show_lines=False,
            border_style="dim",
            title_style="bold",
            header_style="bold dim",
        )
        table.add_column("Extension", style="cyan", min_width=12)
        table.add_column("Count", justify="right", min_width=8)

        # Show top 15 extensions by count
        sorted_exts = sorted(
            summary.language_breakdown.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        for ext, count in sorted_exts[:15]:
            table.add_row(ext, str(count))

        self._out.console.print()
        self._out.console.print(f"[muted]Total tracked files: {summary.file_count:,}[/]")
        self._out.console.print()
        self._out.console.print(table)

        if summary.tree_preview:
            self._out.console.print()
            self._out.console.print("[muted]Tree preview (first 30 files):[/]")
            for line in summary.tree_preview.split("\n")[:30]:
                self._out.console.print(f"  [dim]{line}[/]")

        self._out.console.print()

    # -- Slash-command handlers — v0.4.0 tools -------------------------------

    async def _cmd_tools(self) -> None:
        """List all registered tools."""
        tools = self._registry.all_tools()
        if not tools:
            self._out.console.print("[muted]No tools registered.[/]")
            return

        table = Table(
            title="Available Tools",
            show_lines=False,
            border_style="dim",
            title_style="bold",
            header_style="bold dim",
        )
        table.add_column("Tool", style="cyan", min_width=14)
        table.add_column("Permission", min_width=10)
        table.add_column("Description", style="dim")

        perm_styles = {
            "auto": "[green]auto[/]",
            "ask": "[yellow]ask[/]",
            "deny": "[red]deny[/]",
        }

        for tool in tools:
            perm_display = perm_styles.get(tool.permission.value, tool.permission.value)
            table.add_row(tool.name, perm_display, tool.description)

        self._out.console.print()
        self._out.console.print(table)
        yolo_state = "[bold yellow]on[/]" if self._tool_executor.yolo_mode else "[dim]off[/]"
        self._out.console.print(f"\n[muted]Yolo mode: {yolo_state}[/]")
        self._out.console.print()

    async def _cmd_yolo(self) -> None:
        """Toggle yolo mode (auto-approve all tool executions)."""
        self._tool_executor.yolo_mode = not self._tool_executor.yolo_mode
        if self._tool_executor.yolo_mode:
            self._out.console.print("[bold yellow]Yolo mode: ON[/] — all tools auto-approved")
        else:
            self._out.console.print("[muted]Yolo mode: OFF[/] — tools will ask before executing")

    # -- Slash-command handlers — v0.4.0 crews -------------------------------

    async def _cmd_crew(self, arg: str) -> None:
        """Manage crew configurations: list, load, show."""
        arg = arg.strip()
        if not arg or arg == "list":
            await self._cmd_crew_list()
        elif arg.startswith("load "):
            crew_name = arg[5:].strip()
            await self._cmd_crew_load(crew_name)
        elif arg == "show":
            await self._cmd_crew_show()
        else:
            self._out.print_error(
                f"Unknown crew subcommand: {arg}",
                suggestion="Usage: /crew list | /crew load <name> | /crew show",
            )

    async def _cmd_crew_list(self) -> None:
        """List available crew configurations."""
        ensure_default_crews()
        crews = list_crews()
        if not crews:
            self._out.console.print("[muted]No crew configurations found.[/]")
            return
        self._out.console.print()
        self._out.console.print("[bold]Available Crews:[/]")
        for name in crews:
            active_marker = " [green](active)[/]" if name == self._active_crew_name else ""
            self._out.console.print(f"  [cyan]{name}[/]{active_marker}")
        self._out.console.print()
        self._out.console.print("[muted]Use /crew load <name> to activate a crew[/]")
        self._out.console.print()

    async def _cmd_crew_load(self, name: str) -> None:
        """Load a crew configuration."""
        if not name:
            self._out.print_error("Usage: /crew load <name>")
            return
        ensure_default_crews()
        try:
            config = load_crew(name)
            self._active_crew_name = config.name
            self._active_crew_config = config
            agent_names = ", ".join(config.agents.keys())
            self._out.print_success(
                f"Loaded crew: {config.name} ({len(config.agents)} agents: {agent_names})"
            )
        except SystemExit as exc:
            self._out.print_error(str(exc))

    async def _cmd_crew_show(self) -> None:
        """Show agents in the active crew."""
        if self._active_crew_config is None:
            self._out.console.print(
                "[muted]No crew loaded. Use /crew load <name> first.[/]"
            )
            return

        config = self._active_crew_config
        table = Table(
            title=f"Crew: {config.name}",
            show_lines=False,
            border_style="dim",
            title_style="bold",
            header_style="bold dim",
        )
        table.add_column("Agent", style="cyan", min_width=14)
        table.add_column("Role", min_width=12)
        table.add_column("Model", style="dim", min_width=24)
        table.add_column("Max Tokens", justify="right", min_width=10)

        role_styles = {
            "orchestrator": "[bold blue]orchestrator[/]",
            "specialist": "[green]specialist[/]",
        }

        for name, agent in config.agents.items():
            role_display = role_styles.get(agent.role, agent.role)
            table.add_row(
                name,
                role_display,
                _short_model_name(agent.model),
                str(agent.max_tokens),
            )

        self._out.console.print()
        self._out.console.print(table)
        self._out.console.print(
            f"\n[muted]Budget: ${config.budget_limit_usd:.2f}  |  "
            f"{config.description}[/]"
        )
        self._out.console.print()

    async def _cmd_run(self, task: str) -> None:
        """Execute a task with the active crew."""
        task = task.strip()
        if not task:
            self._out.print_error("Usage: /run <task description>")
            return

        # Auto-load default crew if none is active
        if self._active_crew_config is None:
            ensure_default_crews()
            try:
                config = load_crew("default")
                self._active_crew_name = config.name
                self._active_crew_config = config
                self._out.console.print(
                    f"[muted]Auto-loaded crew: {config.name}[/]"
                )
            except SystemExit as exc:
                self._out.print_error(f"Failed to load default crew: {exc}")
                return

        config = self._active_crew_config
        self._out.console.print(
            f"[muted]Running crew '{config.name}' with {len(config.agents)} agents...[/]"
        )
        self._out.console.print()

        queue: asyncio.Queue = asyncio.Queue()

        async def on_event(event: dict) -> None:
            await queue.put(event)

        engine = CrewEngine(
            api_key=self._api_key,
            crew=config,
            on_event=on_event,
        )

        display = CrewDisplay(
            crew_name=config.name,
            task=task,
            budget=config.budget_limit_usd,
        )

        # Run engine and display concurrently
        async def _run_engine() -> Any:
            result = await engine.execute(task)
            await queue.put({"type": "crew_done", "totalCost": engine.total_cost})
            return result

        engine_task = asyncio.create_task(_run_engine())

        try:
            await display.run(queue)
        except Exception as exc:  # noqa: BLE001
            self._out.print_error(f"Crew display error: {exc}")

        try:
            crew_run = await engine_task
        except Exception as exc:  # noqa: BLE001
            self._out.print_error(f"Crew execution failed: {exc}")
            return

        # Add the crew result to the conversation for context continuity
        if crew_run.final_result:
            self._conversation.add_assistant_message(crew_run.final_result)

    async def _cmd_agents(self) -> None:
        """Alias for /crew show."""
        await self._cmd_crew_show()

    # -- Slash-command handlers — v0.5.0 smart routing -----------------------

    async def _cmd_auto(self) -> None:
        """Toggle automatic smart routing on/off."""
        self._auto_route = not self._auto_route
        state = "[bold green]on[/]" if self._auto_route else "[bold red]off[/]"
        self._out.console.print(f"Smart routing is now {state}")
        if self._auto_route:
            self._out.console.print(
                "[muted]  Prompts will auto-route to the best model per task type[/]"
            )

    async def _cmd_route(self, arg: str) -> None:
        """Show route table, or test routing for a given prompt."""
        if arg.strip():
            decision = self._router.route(arg.strip())
            self._out.console.print(f"[cyan]  {decision.reasoning}[/]")
            self._out.console.print(
                f"[muted]  Confidence: {decision.confidence:.0%}  |  "
                f"Category: {decision.category.value}[/]"
            )
            if decision.suggest_crew:
                self._out.console.print(
                    "[muted]  Tip: Multi-faceted task — try /run for a multi-model crew[/]"
                )
        else:
            table = Table(
                title="Smart Route Table",
                show_lines=False,
                border_style="dim",
                title_style="bold",
                header_style="bold dim",
            )
            table.add_column("Task Type", style="cyan", min_width=20)
            table.add_column("Model", style="green")
            for category, model in self._router.get_route_table().items():
                table.add_row(category, model)
            self._out.console.print()
            self._out.console.print(table)
            state = "[green]on[/]" if self._auto_route else "[red]off[/]"
            self._out.console.print(f"\n[muted]  Auto-routing: {state}  |  Toggle with /auto[/]")
            self._out.console.print()

    # -- Prompt execution ----------------------------------------------------

    async def _handle_prompt(self, text: str) -> None:
        """Stream a user prompt through the active model."""
        clean_text, file_refs = self._extract_file_refs(text)

        for filename, content in file_refs:
            self._conversation.add_file_context(filename, content)
            self._out.console.print(f"[muted]  Loaded {Path(filename).name}[/]")

        if not clean_text:
            if file_refs:
                self._out.console.print("[muted]Files loaded. Send a prompt to continue.[/]")
            return

        self._conversation.add_user_message(clean_text)

        # Smart routing: temporarily switch model if auto_route is on
        original_model = self._model
        routed = False
        if self._auto_route:
            decision = self._router.route(clean_text)
            if decision.model != self._model:
                self._model = decision.model
                routed = True
                self._out.console.print(f"[muted]  \u21af {decision.reasoning}[/]")
                if decision.suggest_crew:
                    self._out.console.print(
                        "[muted]  Tip: Complex task detected \u2014 try /run for multi-model crew[/]"
                    )

        # Append user message to active session if tracking
        if self._session_id:
            try:
                self._session_store.append_message(
                    self._session_id, "user", clean_text,
                )
            except Exception:  # noqa: BLE001
                pass

        messages = self._conversation.get_messages()

        from app.cli.output import StreamingDisplay

        display = StreamingDisplay()
        display.start()

        input_tokens = 0
        output_tokens = 0

        try:
            async for token in _stream_openrouter(self._api_key, self._model, messages):
                if token.startswith("__usage__:"):
                    parts = token.split(":")
                    input_tokens = int(parts[1])
                    output_tokens = int(parts[2])
                else:
                    display.token(token)
            display.finish()
        except httpx.HTTPStatusError as exc:
            display.finish()
            try:
                detail = exc.response.text[:200] if exc.response.text else None
            except httpx.ResponseNotRead:
                detail = f"HTTP {exc.response.status_code}"
            self._out.print_error(
                f"API error: {exc.response.status_code}",
                detail=detail,
                suggestion="Check your API key and model ID",
            )
            self._conversation.remove_last_message()
            return
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            display.finish()
            self._out.print_error(
                "Connection failed",
                detail=str(exc),
                suggestion="Check your network connection and try again",
            )
            self._conversation.remove_last_message()
            return
        except Exception as exc:  # noqa: BLE001
            display.finish()
            self._out.print_error(f"Request failed: {exc}")
            self._conversation.remove_last_message()
            return

        result = display.text
        self._conversation.add_assistant_message(result)

        if not output_tokens:
            output_tokens = max(1, len(result) // 4)
        if not input_tokens:
            input_tokens = self._conversation.estimated_tokens

        self._conversation.tracker.record_request(input_tokens, output_tokens, self._model)

        cost = self._conversation.tracker.estimate_cost(input_tokens, output_tokens, self._model)
        self._out.print_response_footer(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            elapsed=display.elapsed,
        )

        if self._auto_save and result.strip():
            path = self._out.save_result(
                "prompt",
                f"# Prompt ({self._model})\n\n**Prompt:** {clean_text}\n\n{result}",
            )
            self._out.print_saved(path)

        # -- Tool execution loop --
        tool_calls_present = "<tool_call>" in result
        if tool_calls_present and self._tool_executor:
            api_key = self._api_key
            model = self._model

            async def stream_fn(msgs: list[dict[str, str]]) -> tuple[str, int, int]:
                from app.cli.output import StreamingDisplay as SD
                display2 = SD()
                display2.start()
                in_t = 0
                out_t = 0
                try:
                    async for tok in _stream_openrouter(api_key, model, msgs):
                        if tok.startswith("__usage__:"):
                            parts = tok.split(":")
                            in_t = int(parts[1])
                            out_t = int(parts[2])
                        else:
                            display2.token(tok)
                    display2.finish()
                except Exception:  # noqa: BLE001
                    display2.finish()
                return display2.text, in_t, out_t

            try:
                working_messages = self._conversation.get_messages()
                final_text, updated_messages = await self._tool_executor.process_response(
                    result, stream_fn, working_messages,
                )
                # Sync the updated messages back into the conversation
                # The tool executor mutates the messages list by appending
                # assistant+user (tool result) pairs. We need to add those
                # to the conversation object.
                existing_count = len(self._conversation.get_messages())
                for msg in updated_messages[existing_count:]:
                    if msg["role"] == "assistant":
                        self._conversation.add_assistant_message(msg["content"])
                    elif msg["role"] == "user":
                        self._conversation.add_user_message(msg["content"])

                # Record usage for tool rounds (approximate)
                if final_text != result:
                    tool_out_tokens = max(1, len(final_text) // 4)
                    self._conversation.tracker.record_request(
                        0, tool_out_tokens, self._model,
                    )
                    result = final_text
            except Exception as exc:  # noqa: BLE001
                self._out.print_error(f"Tool execution failed: {exc}")

        # Append assistant response to active session
        if self._session_id:
            try:
                self._session_store.append_message(
                    self._session_id,
                    "assistant",
                    result,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            except Exception:  # noqa: BLE001
                pass

        # Restore model after smart routing
        if routed:
            self._model = original_model

    # -- Command router ------------------------------------------------------

    async def _dispatch(self, raw: str) -> bool:
        """Parse and dispatch input. Returns False if the REPL should exit."""
        text = raw.strip()

        if not text:
            return True

        if text.startswith("/"):
            cmd, _, arg = text.partition(" ")
            cmd = cmd.lower()

            if cmd in ("/quit", "/exit"):
                return False
            if cmd == "/model":
                await self._cmd_model()
            elif cmd == "/compare":
                await self._cmd_compare(arg)
            elif cmd == "/split":
                await self._cmd_split(arg)
            elif cmd == "/critique":
                await self._cmd_critique(arg)
            elif cmd in ("/tokens", "/cost"):
                await self._cmd_tokens()
            elif cmd == "/status":
                await self._cmd_status()
            elif cmd == "/new":
                await self._cmd_new()
            elif cmd == "/context":
                await self._cmd_context()
            elif cmd == "/help":
                await self._cmd_help()
            elif cmd == "/clear":
                await self._cmd_clear()
            elif cmd == "/save":
                await self._cmd_save()
            # v0.4.0 — sessions
            elif cmd == "/save-session":
                await self._cmd_save_session(arg)
            elif cmd == "/load-session":
                await self._cmd_load_session(arg)
            elif cmd == "/sessions":
                await self._cmd_sessions()
            elif cmd == "/resume":
                await self._cmd_resume()
            elif cmd == "/delete-session":
                await self._cmd_delete_session(arg)
            # v0.4.0 — git
            elif cmd == "/git":
                await self._cmd_git()
            elif cmd == "/diff":
                await self._cmd_diff(arg)
            elif cmd == "/repo":
                await self._cmd_repo()
            # v0.4.0 — tools
            elif cmd == "/tools":
                await self._cmd_tools()
            elif cmd == "/yolo":
                await self._cmd_yolo()
            # v0.4.0 — crews
            elif cmd == "/crew":
                await self._cmd_crew(arg)
            elif cmd == "/run":
                await self._cmd_run(arg)
            elif cmd == "/agents":
                await self._cmd_agents()
            # v0.5.0 — smart routing
            elif cmd == "/auto":
                await self._cmd_auto()
            elif cmd == "/route":
                await self._cmd_route(arg)
            else:
                self._out.print_error(
                    f"Unknown command: {cmd}",
                    suggestion="Type /help for available commands",
                )
            return True

        await self._handle_prompt(text)
        return True

    # -- Main loop -----------------------------------------------------------

    async def run(self) -> None:
        """Start the interactive REPL. Blocks until exit."""
        self._session_start = time.monotonic()

        # -- Git detection --
        self._git_root = detect_git_repo()
        if self._git_root is not None:
            self._git_info = collect_git_info(self._git_root)
            git_block = format_git_context(self._git_info)
            current_prompt = self._conversation.system_prompt
            self._conversation.set_system_prompt(current_prompt + "\n\n" + git_block)
            modified_count = len(self._git_info.modified_files)
            self._out.console.print(
                f"[muted]Git: {self._git_info.branch} "
                f"({self._git_info.root.name}, {modified_count} modified)[/]"
            )

        # -- Tool system prompt injection --
        tool_prompt = self._tool_executor.get_tool_system_prompt()
        current_prompt = self._conversation.system_prompt
        self._conversation.set_system_prompt(current_prompt + tool_prompt)

        # -- Auto-resume --
        cfg = load_config()
        if cfg.auto_resume:
            self._auto_resume_session()

        # -- Ensure default crews --
        ensure_default_crews()

        self._out.console.print(
            "[muted]Type a prompt to chat. /help for commands.[/]"
        )
        self._out.console.print()

        while True:
            short_name = _short_model_name(self._model)
            prompt_html = f"<style fg='ansibrightcyan'>{short_name}</style> <b><style fg='ansibrightgreen'>&#x276f;</style></b> "

            try:
                with patch_stdout():
                    raw = await self._session.prompt_async(
                        HTML(prompt_html),
                        bottom_toolbar=self._bottom_toolbar,
                    )
            except KeyboardInterrupt:
                now = time.monotonic()
                if self._last_interrupt and (now - self._last_interrupt) < 2.0:
                    break
                self._last_interrupt = now
                self._out.console.print("[muted]Press Ctrl+C again to exit.[/]")
                continue
            except EOFError:
                break

            self._last_interrupt = 0.0

            should_continue = await self._dispatch(raw)
            if not should_continue:
                break

        # -- Auto-save session on exit --
        if self._conversation.message_count > 0:
            try:
                sid = self._session_store.save_session(
                    self._conversation, self._model,
                )
                self._out.console.print(f"[muted]Session saved: {sid[:12]}[/]")
            except Exception:  # noqa: BLE001
                pass

        self._print_exit_summary()

    def _print_exit_summary(self) -> None:
        """Print session stats and goodbye on exit."""
        t = self._conversation.tracker
        elapsed = time.monotonic() - self._session_start if self._session_start else 0
        sep = "\u2500" * 40

        self._out.console.print()
        self._out.console.print(f"[separator]{sep}[/]")

        if t.request_count > 0:
            self._out.console.print(
                f"[muted]Session: {t.total_tokens:,} tokens / "
                f"${t.session_cost:.4f} ({t.request_count} requests)[/]"
            )

        self._out.console.print(
            f"[muted]Session: {_format_duration(elapsed)}. Goodbye.[/]"
        )
