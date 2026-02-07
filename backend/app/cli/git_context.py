"""Git repository awareness for the code-swap CLI.

All git operations are **read-only** and wrapped in try/except so the CLI
degrades gracefully when git is not installed or the working directory is
not inside a repository.
"""

from __future__ import annotations

import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class GitInfo:
    """Git repository state."""

    root: Path
    branch: str
    remote: str | None
    recent_commits: list[str]  # last 5 one-line commits
    modified_files: list[str]
    staged_files: list[str]
    untracked_files: list[str]


@dataclass(slots=True)
class RepoSummary:
    """High-level repo structure."""

    root: Path
    file_count: int
    language_breakdown: dict[str, int]  # extension -> count
    tree_preview: str  # first 30 lines of tree output


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TIMEOUT = 10  # seconds per subprocess call


def _git(
    *args: str,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    """Run a read-only git command and return the CompletedProcess."""
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
        cwd=cwd,
    )


def _git_lines(*args: str, cwd: Path) -> list[str]:
    """Run a git command and return non-empty stdout lines."""
    proc = _git(*args, cwd=cwd)
    if proc.returncode != 0:
        return []
    return [ln for ln in proc.stdout.splitlines() if ln]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_git_repo(cwd: Path | None = None) -> Path | None:
    """Return the git repo root for *cwd*, or ``None`` if not in a repo.

    Gracefully returns ``None`` when git is not installed.
    """
    cwd = cwd or Path.cwd()
    try:
        proc = _git("rev-parse", "--show-toplevel", cwd=cwd)
        if proc.returncode == 0:
            return Path(proc.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # git not installed or timed out
        pass
    return None


def collect_git_info(cwd: Path) -> GitInfo:
    """Collect current git state for *cwd* (branch, remote, diffs, etc.)."""
    try:
        branch_lines = _git_lines("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)
        branch = branch_lines[0] if branch_lines else "unknown"

        remote_proc = _git("remote", "get-url", "origin", cwd=cwd)
        remote = remote_proc.stdout.strip() if remote_proc.returncode == 0 else None

        recent_commits = _git_lines("log", "--oneline", "-5", cwd=cwd)
        modified_files = _git_lines("diff", "--name-only", cwd=cwd)
        staged_files = _git_lines("diff", "--cached", "--name-only", cwd=cwd)
        untracked_files = _git_lines(
            "ls-files", "--others", "--exclude-standard", cwd=cwd
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return GitInfo(
            root=cwd,
            branch="unknown",
            remote=None,
            recent_commits=[],
            modified_files=[],
            staged_files=[],
            untracked_files=[],
        )

    return GitInfo(
        root=cwd,
        branch=branch,
        remote=remote,
        recent_commits=recent_commits,
        modified_files=modified_files,
        staged_files=staged_files,
        untracked_files=untracked_files,
    )


def format_git_context(info: GitInfo) -> str:
    """Format *info* as an XML block suitable for system-prompt injection."""
    commits = "\n".join(f"  {c}" for c in info.recent_commits) or "  (none)"
    modified = ", ".join(info.modified_files) or "none"
    staged = ", ".join(info.staged_files) or "none"

    return (
        "<git_context>\n"
        f"Repository: {info.root.name}\n"
        f"Branch: {info.branch}\n"
        f"Remote: {info.remote or 'none'}\n"
        "\n"
        "Recent commits:\n"
        f"{commits}\n"
        "\n"
        f"Modified files: {modified}\n"
        f"Staged files: {staged}\n"
        "</git_context>"
    )


def collect_repo_summary(cwd: Path) -> RepoSummary:
    """Build a high-level structural summary of the repo at *cwd*."""
    try:
        tracked = _git_lines("ls-files", cwd=cwd)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return RepoSummary(
            root=cwd,
            file_count=0,
            language_breakdown={},
            tree_preview="",
        )

    file_count = len(tracked)

    # Count files by extension
    ext_counter: Counter[str] = Counter()
    for path_str in tracked:
        ext = Path(path_str).suffix.lower()
        ext_counter[ext if ext else "(no ext)"] += 1

    # Sort by count descending for readability
    language_breakdown = dict(ext_counter.most_common())

    # Tree preview — first 30 tracked paths
    try:
        tree_lines = _git_lines(
            "ls-tree", "-r", "--name-only", "HEAD", cwd=cwd
        )
        tree_preview = "\n".join(tree_lines[:30])
    except (FileNotFoundError, subprocess.TimeoutExpired):
        tree_preview = ""

    return RepoSummary(
        root=cwd,
        file_count=file_count,
        language_breakdown=language_breakdown,
        tree_preview=tree_preview,
    )


def get_full_diff(cwd: Path, staged_only: bool = False) -> str:
    """Return the current diff (or staged diff) as a string.

    Output is truncated at 8 000 characters to avoid blowing up the context
    window when injected into a prompt.
    """
    _MAX_CHARS = 8_000

    try:
        args = ["diff", "--cached"] if staged_only else ["diff"]
        proc = _git(*args, cwd=cwd)
        if proc.returncode != 0:
            return ""
        diff = proc.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""

    if len(diff) > _MAX_CHARS:
        return diff[:_MAX_CHARS] + "\n... (truncated)"
    return diff
