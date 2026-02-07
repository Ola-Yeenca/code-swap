"""Tool execution framework for AI-driven tool use in the code-swap CLI.

Provides a registry of built-in tools (shell, read, write, test, lint) that
the AI assistant can invoke during conversations.  Each tool declares a
permission level that determines whether the user is prompted before execution.

Tool calls are parsed from ``<tool_call>`` XML blocks in assistant responses
and results are injected back as ``<tool_result>`` blocks.
"""

from __future__ import annotations

import enum
import json
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


# ---------------------------------------------------------------------------
# Permission levels
# ---------------------------------------------------------------------------

class PermissionLevel(enum.Enum):
    """Controls whether a tool execution requires user approval."""

    AUTO = "auto"   # Execute without asking
    ASK = "ask"     # Prompt user before executing
    DENY = "deny"   # Never execute


# ---------------------------------------------------------------------------
# Tool result
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ToolResult:
    """Outcome of a single tool invocation."""

    success: bool
    output: str
    error: str | None = None


# ---------------------------------------------------------------------------
# Tool base class
# ---------------------------------------------------------------------------

class Tool(ABC):
    """Abstract base for every built-in tool."""

    name: str
    description: str
    permission: PermissionLevel

    @abstractmethod
    async def execute(self, arguments: dict, cwd: Path) -> ToolResult:
        """Run the tool with *arguments* inside *cwd* and return a result."""
        ...


# ---------------------------------------------------------------------------
# Dangerous-command blocklist (used by ShellTool)
# ---------------------------------------------------------------------------

_DANGEROUS_PATTERNS: list[str] = [
    r"rm\s+-rf\s+/",
    r"rm\s+-rf\s+~",
    r"mkfs\b",
    r"dd\s+if=",
    r"shutdown\b",
    r"reboot\b",
    r":()\{\s*:\|:&\s*\};:",       # fork bomb
    r">\s*/dev/sd",
    r"chmod\s+-R\s+777\s+/",
]


def _is_dangerous(command: str) -> bool:
    """Return ``True`` if *command* matches a known destructive pattern."""
    return any(re.search(p, command) for p in _DANGEROUS_PATTERNS)


# ---------------------------------------------------------------------------
# Built-in tools
# ---------------------------------------------------------------------------

_OUTPUT_CAP = 10_000      # max chars returned from shell output
_FILE_READ_CAP = 20_000   # max chars when reading a file
_DEFAULT_TIMEOUT = 30     # seconds
_MAX_TIMEOUT = 120        # seconds
_TEST_TIMEOUT = 120       # seconds


class ShellTool(Tool):
    """Execute a shell command inside the working directory."""

    name = "shell"
    description = (
        "Run a shell command. Arguments: command (str, required), "
        "timeout (int, optional, default 30, max 120)."
    )
    permission = PermissionLevel.ASK

    async def execute(self, arguments: dict, cwd: Path) -> ToolResult:
        command: str | None = arguments.get("command")
        if not command:
            return ToolResult(success=False, output="", error="Missing required argument: command")

        if _is_dangerous(command):
            return ToolResult(
                success=False,
                output="",
                error=f"Blocked: command matches a dangerous pattern: {command}",
            )

        timeout = min(int(arguments.get("timeout", _DEFAULT_TIMEOUT)), _MAX_TIMEOUT)

        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
            stdout = proc.stdout[:_OUTPUT_CAP] if proc.stdout else ""
            stderr = proc.stderr[:_OUTPUT_CAP] if proc.stderr else ""

            if proc.returncode == 0:
                return ToolResult(success=True, output=stdout or "(no output)")
            else:
                combined = f"Exit code {proc.returncode}\n"
                if stdout:
                    combined += f"stdout:\n{stdout}\n"
                if stderr:
                    combined += f"stderr:\n{stderr}"
                return ToolResult(success=False, output="", error=combined.strip())

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error=f"Command timed out after {timeout}s",
            )
        except Exception as exc:
            return ToolResult(success=False, output="", error=str(exc))


class ReadFileTool(Tool):
    """Read the contents of a file within the working directory."""

    name = "read_file"
    description = "Read a file's contents. Arguments: path (str, required)."
    permission = PermissionLevel.AUTO

    async def execute(self, arguments: dict, cwd: Path) -> ToolResult:
        raw_path: str | None = arguments.get("path")
        if not raw_path:
            return ToolResult(success=False, output="", error="Missing required argument: path")

        target = (cwd / raw_path).resolve()
        if not target.is_relative_to(cwd.resolve()):
            return ToolResult(
                success=False,
                output="",
                error="Path traversal denied: path must be within the working directory",
            )

        if not target.exists():
            return ToolResult(success=False, output="", error=f"File not found: {raw_path}")
        if not target.is_file():
            return ToolResult(success=False, output="", error=f"Not a regular file: {raw_path}")

        try:
            content = target.read_text(errors="replace")
            lines = content.count("\n") + 1
            chars = len(content)
            truncated = content[:_FILE_READ_CAP]
            suffix = ""
            if chars > _FILE_READ_CAP:
                suffix = f"\n... (truncated, showing {_FILE_READ_CAP:,} of {chars:,} chars)"
            return ToolResult(
                success=True,
                output=f"{truncated}{suffix}\n\n({lines:,} lines, {chars:,} chars)",
            )
        except Exception as exc:
            return ToolResult(success=False, output="", error=str(exc))


class WriteFileTool(Tool):
    """Write content to a file within the working directory."""

    name = "write_file"
    description = (
        "Write content to a file. Creates parent directories as needed. "
        "Arguments: path (str, required), content (str, required)."
    )
    permission = PermissionLevel.ASK

    async def execute(self, arguments: dict, cwd: Path) -> ToolResult:
        raw_path: str | None = arguments.get("path")
        content: str | None = arguments.get("content")
        if not raw_path:
            return ToolResult(success=False, output="", error="Missing required argument: path")
        if content is None:
            return ToolResult(success=False, output="", error="Missing required argument: content")

        target = (cwd / raw_path).resolve()
        if not target.is_relative_to(cwd.resolve()):
            return ToolResult(
                success=False,
                output="",
                error="Path traversal denied: path must be within the working directory",
            )

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            bytes_written = len(content.encode())
            return ToolResult(
                success=True,
                output=f"Wrote {bytes_written:,} bytes to {raw_path}",
            )
        except Exception as exc:
            return ToolResult(success=False, output="", error=str(exc))


class RunTestsTool(Tool):
    """Auto-detect and run the project's test suite."""

    name = "run_tests"
    description = (
        "Detect the test runner and execute tests. "
        "Arguments: args (str, optional extra arguments)."
    )
    permission = PermissionLevel.ASK

    async def execute(self, arguments: dict, cwd: Path) -> ToolResult:
        extra_args = arguments.get("args", "")
        command = self._detect_runner(cwd, extra_args)
        if command is None:
            return ToolResult(
                success=False,
                output="",
                error="No test runner detected in this project",
            )

        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=_TEST_TIMEOUT,
                cwd=cwd,
            )
            stdout = proc.stdout[:_OUTPUT_CAP] if proc.stdout else ""
            stderr = proc.stderr[:_OUTPUT_CAP] if proc.stderr else ""
            combined = stdout
            if stderr:
                combined += f"\n{stderr}" if combined else stderr

            if proc.returncode == 0:
                return ToolResult(success=True, output=combined or "Tests passed (no output)")
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Tests failed (exit {proc.returncode}):\n{combined}".strip(),
                )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error=f"Tests timed out after {_TEST_TIMEOUT}s",
            )
        except Exception as exc:
            return ToolResult(success=False, output="", error=str(exc))

    @staticmethod
    def _detect_runner(cwd: Path, extra_args: str) -> str | None:
        """Return a shell command for the detected test framework, or ``None``."""
        suffix = f" {extra_args}" if extra_args else ""

        # Python: pytest
        if (cwd / "pytest.ini").exists():
            return f"python -m pytest{suffix}"
        pyproject = cwd / "pyproject.toml"
        if pyproject.exists():
            try:
                text = pyproject.read_text()
                if "pytest" in text or "[tool.pytest" in text:
                    return f"python -m pytest{suffix}"
            except OSError:
                pass

        # JavaScript/TypeScript: jest or vitest
        pkg_json = cwd / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text())
                all_deps = {
                    **pkg.get("dependencies", {}),
                    **pkg.get("devDependencies", {}),
                }
                if "vitest" in all_deps:
                    return f"npx vitest run{suffix}"
                if "jest" in all_deps:
                    return f"npx jest{suffix}"
            except (OSError, json.JSONDecodeError):
                pass

        # Rust
        if (cwd / "Cargo.toml").exists():
            return f"cargo test{suffix}"

        # Go
        if (cwd / "go.mod").exists():
            return f"go test ./...{suffix}"

        return None


class LintTool(Tool):
    """Auto-detect and run the project's linter."""

    name = "lint"
    description = (
        "Detect the linter and run it. "
        "Arguments: args (str, optional extra arguments)."
    )
    permission = PermissionLevel.ASK

    async def execute(self, arguments: dict, cwd: Path) -> ToolResult:
        extra_args = arguments.get("args", "")
        command = self._detect_linter(cwd, extra_args)
        if command is None:
            return ToolResult(
                success=False,
                output="",
                error="No linter detected in this project",
            )

        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=_TEST_TIMEOUT,
                cwd=cwd,
            )
            stdout = proc.stdout[:_OUTPUT_CAP] if proc.stdout else ""
            stderr = proc.stderr[:_OUTPUT_CAP] if proc.stderr else ""
            combined = stdout
            if stderr:
                combined += f"\n{stderr}" if combined else stderr

            if proc.returncode == 0:
                return ToolResult(success=True, output=combined or "No lint issues found")
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Lint issues found (exit {proc.returncode}):\n{combined}".strip(),
                )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                output="",
                error=f"Linter timed out after {_TEST_TIMEOUT}s",
            )
        except Exception as exc:
            return ToolResult(success=False, output="", error=str(exc))

    @staticmethod
    def _detect_linter(cwd: Path, extra_args: str) -> str | None:
        """Return a shell command for the detected linter, or ``None``."""
        suffix = f" {extra_args}" if extra_args else ""

        # Python: ruff
        try:
            subprocess.run(
                ["ruff", "--version"],
                capture_output=True,
                timeout=5,
            )
            return f"ruff check .{suffix}"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # JavaScript/TypeScript: eslint
        if (cwd / "package.json").exists():
            return f"npx eslint .{suffix}"

        # Go: golangci-lint
        if (cwd / "go.mod").exists():
            return f"golangci-lint run{suffix}"

        return None


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

_BUILTIN_TOOLS: Sequence[type[Tool]] = [
    ShellTool,
    ReadFileTool,
    WriteFileTool,
    RunTestsTool,
    LintTool,
]


class ToolRegistry:
    """Registry that maps tool names to ``Tool`` instances.

    On construction every built-in tool is automatically registered.
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        for tool_cls in _BUILTIN_TOOLS:
            tool = tool_cls()
            self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Look up a tool by *name*, returning ``None`` if not found."""
        return self._tools.get(name)

    def all_tools(self) -> list[Tool]:
        """Return every registered tool."""
        return list(self._tools.values())

    def tool_descriptions(self) -> str:
        """Format the tool list for inclusion in system prompts.

        Returns a multi-line string describing each tool, its permission
        level, and a short description.
        """
        lines: list[str] = ["Available tools:"]
        for tool in self._tools.values():
            perm = tool.permission.value
            lines.append(f"  - {tool.name} [{perm}]: {tool.description}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool-call parsing
# ---------------------------------------------------------------------------

def parse_tool_calls(text: str) -> list[dict]:
    """Extract tool calls from ``<tool_call>`` XML blocks in *text*.

    Expected format::

        <tool_call>{"tool": "shell", "arguments": {"command": "ls"}}</tool_call>

    Returns a list of parsed dicts.  Malformed JSON blocks are silently
    skipped.
    """
    pattern = r"<tool_call>\s*(\{.*?\})\s*</tool_call>"
    matches = re.findall(pattern, text, re.DOTALL)
    calls: list[dict] = []
    for m in matches:
        try:
            calls.append(json.loads(m))
        except json.JSONDecodeError:
            continue
    return calls


def format_tool_result(tool_name: str, result: ToolResult) -> str:
    """Format a ``ToolResult`` as a ``<tool_result>`` XML block.

    This string is injected into the conversation as a user message so the
    model can see the outcome of its tool call.
    """
    success = "true" if result.success else "false"
    content = result.output if result.success else (result.error or "Unknown error")
    return f'<tool_result tool="{tool_name}" success="{success}">\n{content}\n</tool_result>'
