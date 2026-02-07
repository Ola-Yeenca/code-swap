"""Native installer for the code-swap CLI.

Detects the best available tool installer (uv > pipx > pip), runs the
install, ensures ``~/.local/bin`` is on ``PATH``, and verifies the result.

Usage::

    code-swap install              # auto-detect best method
    code-swap install --method uv  # force a specific method
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from app.cli.output import console, print_error, print_info, print_success, print_warning

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TAG = "# Added by code-swap"
_LOCAL_BIN = Path.home() / ".local" / "bin"

# Map installer names to the command used to check availability.
_INSTALLERS = ("uv", "pipx", "pip")


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_installer(preference: str = "auto") -> str | None:
    """Return the best available installer name.

    Parameters
    ----------
    preference:
        ``"auto"`` tries uv -> pipx -> pip.  Otherwise forces the given
        tool (returns ``None`` if it isn't available).
    """
    if preference != "auto":
        return preference if shutil.which(preference) else None

    for tool in _INSTALLERS:
        if shutil.which(tool):
            return tool
    return None


# ---------------------------------------------------------------------------
# Stale entry cleanup
# ---------------------------------------------------------------------------

def _remove_stale_zshrc_entry() -> int:
    """Remove old manual PATH hacks from shell RC files.

    Looks for lines containing both ``code-swap`` (or ``code_swap``) and
    ``export PATH`` that do NOT carry our managed tag.  Returns the number
    of lines removed.
    """
    removed = 0
    for rc_name in _shell_rc_candidates():
        rc = Path.home() / rc_name
        if not rc.is_file():
            continue
        lines = rc.read_text(encoding="utf-8").splitlines(keepends=True)
        cleaned: list[str] = []
        for line in lines:
            low = line.lower()
            if (
                ("code-swap" in low or "code_swap" in low)
                and "export path" in low
                and _TAG not in line
            ):
                removed += 1
                continue
            cleaned.append(line)
        if removed:
            rc.write_text("".join(cleaned), encoding="utf-8")
    return removed


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

def run_install(method: str) -> bool:
    """Run the install using the given method.  Returns True on success."""
    # Find the project root (directory containing pyproject.toml).
    project_root = _find_project_root()
    if project_root is None:
        print_error(
            "Cannot find project root",
            suggestion="Run this command from the code-swap repository",
        )
        return False

    console.print(f"[muted]Installing via [bold]{method}[/bold]...[/]")

    cmd: list[str]
    if method == "uv":
        cmd = ["uv", "tool", "install", "--force", str(project_root)]
    elif method == "pipx":
        cmd = ["pipx", "install", "--force", str(project_root)]
    else:
        # pip --user install
        cmd = [sys.executable, "-m", "pip", "install", "--user", str(project_root)]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        print_error(f"{method} not found on PATH")
        return False
    except subprocess.TimeoutExpired:
        print_error("Install timed out after 120 seconds")
        return False

    if result.returncode != 0:
        print_error(
            f"{method} install failed (exit {result.returncode})",
            detail=(result.stderr or result.stdout)[:300],
        )
        return False

    console.print(f"[muted]{result.stdout.strip()[:200]}[/]")
    return True


# ---------------------------------------------------------------------------
# PATH management
# ---------------------------------------------------------------------------

def _ensure_path_entry() -> bool:
    """Add ``~/.local/bin`` to PATH in the shell RC file if not present.

    Returns True if an entry was added.
    """
    local_bin = str(_LOCAL_BIN)

    # Already on PATH?
    if local_bin in os.environ.get("PATH", "").split(os.pathsep):
        return False

    rc = _primary_shell_rc()
    if rc is None:
        print_warning(
            "Could not determine shell RC file",
            detail="Add ~/.local/bin to your PATH manually",
        )
        return False

    # Check if entry already exists in the file.
    if rc.is_file():
        content = rc.read_text(encoding="utf-8")
        if _TAG in content:
            return False
    else:
        content = ""

    entry = f'\nexport PATH="$HOME/.local/bin:$PATH"  {_TAG}\n'

    with rc.open("a", encoding="utf-8") as f:
        f.write(entry)

    print_info(f"Added ~/.local/bin to PATH in {rc}")
    return True


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def _verify_install() -> bool:
    """Check that ``code-swap`` is reachable on PATH."""
    return shutil.which("code-swap") is not None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def install_pipeline(preference: str = "auto") -> bool:
    """Full install pipeline.  Returns True on overall success."""
    # 1. Detect installer
    method = detect_installer(preference)
    if method is None:
        print_error(
            "No suitable installer found",
            detail="Looked for: uv, pipx, pip",
            suggestion="Install uv (recommended): curl -LsSf https://astral.sh/uv/install.sh | sh",
        )
        return False

    print_info(f"Using installer: {method}")

    # 2. Remove stale PATH hacks
    removed = _remove_stale_zshrc_entry()
    if removed:
        console.print(f"[muted]Cleaned {removed} stale PATH entries from shell RC[/]")

    # 3. Run install
    if not run_install(method):
        return False

    # 4. Ensure PATH
    _ensure_path_entry()

    # 5. Verify
    if _verify_install():
        print_success("code-swap installed successfully!")
        console.print(f"[muted]  Location: {shutil.which('code-swap')}[/]")
        console.print("[muted]  Open a new terminal, then run: code-swap[/]")
        return True

    # Installed but not yet on PATH in current shell.
    print_warning(
        "Installed, but 'code-swap' not found on current PATH",
        detail="Open a new terminal or run: source ~/.zshrc",
    )
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_project_root() -> Path | None:
    """Walk up from this file to find the directory containing pyproject.toml."""
    candidate = Path(__file__).resolve().parent
    for _ in range(10):
        if (candidate / "pyproject.toml").exists():
            return candidate
        candidate = candidate.parent
    return None


def _shell_rc_candidates() -> list[str]:
    """Return shell RC filenames to check."""
    shell = os.environ.get("SHELL", "")
    if "zsh" in shell:
        return [".zshrc", ".zprofile"]
    if "bash" in shell:
        if platform.system() == "Darwin":
            return [".zprofile", ".bash_profile", ".bashrc"]
        return [".bashrc", ".bash_profile"]
    return [".zshrc", ".bashrc", ".profile"]


def _primary_shell_rc() -> Path | None:
    """Return the primary shell RC file path."""
    candidates = _shell_rc_candidates()
    for name in candidates:
        path = Path.home() / name
        if path.is_file():
            return path
    # Fall back to creating the first candidate.
    if candidates:
        return Path.home() / candidates[0]
    return None
