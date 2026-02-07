"""Persistent JSONL-based session storage for the code-swap CLI.

Each session is stored as a single `{session_id}.jsonl` file under
``~/.code_swap/sessions/``.  An ``index.json`` beside them keeps lightweight
metadata so listing sessions never requires reading every JSONL file.

File format
-----------
Line 1 (header):
    {"type": "header", "meta": {<SessionMeta fields>}, "system_prompt": "..."}

Line 2+ (messages):
    {"type": "message", "role": "user|assistant", "content": "...",
     "timestamp": "...", "input_tokens": 0, "output_tokens": 0}
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SESSIONS_DIR: Path = Path.home() / ".code_swap" / "sessions"
INDEX_PATH: Path = SESSIONS_DIR / "index.json"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SessionMeta:
    """Lightweight metadata kept in the index for every saved session."""

    session_id: str
    name: str
    model: str
    created_at: str   # ISO-8601
    updated_at: str   # ISO-8601
    message_count: int
    total_tokens: int
    total_cost: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Return the current UTC time as a compact ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _auto_name(first_user_content: str) -> str:
    """Derive a short session name from the first user message."""
    name = first_user_content.strip().replace("\n", " ")
    if len(name) > 40:
        name = name[:40].rstrip() + "..."
    return name or "untitled"


def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.jsonl"


# ---------------------------------------------------------------------------
# SessionStore
# ---------------------------------------------------------------------------


class SessionStore:
    """JSONL-based persistent session storage."""

    def __init__(self) -> None:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # -- public API --------------------------------------------------------

    def save_session(
        self,
        conversation,
        model: str,
        name: str | None = None,
    ) -> str:
        """Full write of a Conversation to a JSONL file.

        Parameters
        ----------
        conversation:
            A ``Conversation`` instance from ``app.cli.conversation``.
        model:
            The model slug used in this session (e.g. ``anthropic/claude-sonnet-4-5``).
        name:
            Human-readable label.  If *None*, auto-generated from the first
            user message.

        Returns
        -------
        str
            The generated ``session_id``.
        """
        session_id = uuid.uuid4().hex
        now = _now_iso()

        # Collect non-system messages from the conversation.
        messages: list[dict] = []
        first_user_content: str = ""
        for msg_dict in conversation.get_messages():
            if msg_dict["role"] == "system":
                continue
            if not first_user_content and msg_dict["role"] == "user":
                first_user_content = msg_dict["content"]
            messages.append(msg_dict)

        if name is None:
            name = _auto_name(first_user_content)

        tracker = conversation.tracker
        meta = SessionMeta(
            session_id=session_id,
            name=name,
            model=model,
            created_at=now,
            updated_at=now,
            message_count=len(messages),
            total_tokens=tracker.total_tokens,
            total_cost=tracker.session_cost,
        )

        # Write JSONL file ------------------------------------------------
        path = _session_path(session_id)
        try:
            with path.open("w", encoding="utf-8") as fh:
                # Header line
                header = {
                    "type": "header",
                    "meta": asdict(meta),
                    "system_prompt": conversation.system_prompt,
                }
                fh.write(json.dumps(header, ensure_ascii=False) + "\n")

                # Message lines
                for msg in messages:
                    line = {
                        "type": "message",
                        "role": msg["role"],
                        "content": msg["content"],
                        "timestamp": now,
                        "input_tokens": 0,
                        "output_tokens": 0,
                    }
                    fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        except OSError:
            log.exception("Failed to write session file %s", path)
            raise

        self._update_index(meta)
        return session_id

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Append a single message line to an existing session file.

        This is the crash-safe incremental path: if the process dies mid-write
        the worst case is one truncated trailing line which ``load_session``
        gracefully skips.
        """
        path = _session_path(session_id)
        if not path.exists():
            log.warning("Session file not found for append: %s", session_id)
            return

        line = {
            "type": "message",
            "role": role,
            "content": content,
            "timestamp": _now_iso(),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        except OSError:
            log.exception("Failed to append to session %s", session_id)
            return

        # Refresh index with updated counts.
        self._refresh_meta_from_file(session_id)

    def load_session(self, session_id: str) -> dict:
        """Read a JSONL session file and return its contents.

        Returns
        -------
        dict
            ``{"meta": SessionMeta, "system_prompt": str, "messages": [dict]}``

        Raises
        ------
        FileNotFoundError
            If the session file does not exist.
        """
        path = _session_path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")

        meta: SessionMeta | None = None
        system_prompt: str = ""
        messages: list[dict] = []

        with path.open("r", encoding="utf-8") as fh:
            for lineno, raw_line in enumerate(fh, 1):
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    obj = json.loads(raw_line)
                except json.JSONDecodeError:
                    log.warning(
                        "Skipping corrupt line %d in %s", lineno, path.name
                    )
                    continue

                if obj.get("type") == "header":
                    meta_dict = obj.get("meta", {})
                    meta = SessionMeta(**meta_dict)
                    system_prompt = obj.get("system_prompt", "")
                elif obj.get("type") == "message":
                    messages.append(
                        {
                            "role": obj["role"],
                            "content": obj["content"],
                            "timestamp": obj.get("timestamp", ""),
                            "input_tokens": obj.get("input_tokens", 0),
                            "output_tokens": obj.get("output_tokens", 0),
                        }
                    )

        if meta is None:
            raise ValueError(f"Session file missing header: {session_id}")

        return {
            "meta": meta,
            "system_prompt": system_prompt,
            "messages": messages,
        }

    def list_sessions(self) -> list[SessionMeta]:
        """Return all sessions sorted by ``updated_at`` descending."""
        index = self._load_index()
        sessions = []
        for entry in index:
            try:
                sessions.append(SessionMeta(**entry))
            except TypeError:
                log.warning("Skipping malformed index entry: %s", entry)
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def get_latest(self) -> SessionMeta | None:
        """Return the most recently updated session, or *None*."""
        sessions = self.list_sessions()
        return sessions[0] if sessions else None

    def delete_session(self, session_id: str) -> bool:
        """Delete a session file and remove it from the index.

        Returns *True* if the session existed and was deleted.
        """
        path = _session_path(session_id)
        deleted = False
        if path.exists():
            try:
                path.unlink()
                deleted = True
            except OSError:
                log.exception("Failed to delete session file %s", path)
        self._remove_from_index(session_id)
        return deleted

    def prune_sessions(self, max_sessions: int = 50) -> int:
        """Delete the oldest *unnamed* sessions beyond *max_sessions*.

        "Unnamed" means the name was auto-generated (we treat any session
        whose name ends with ``...`` or equals ``"untitled"`` as unnamed).

        Returns the number of sessions deleted.
        """
        sessions = self.list_sessions()
        if len(sessions) <= max_sessions:
            return 0

        # Candidates for pruning: unnamed sessions, oldest first.
        unnamed = [
            s
            for s in reversed(sessions)  # oldest first
            if s.name.endswith("...") or s.name == "untitled"
        ]

        to_delete = len(sessions) - max_sessions
        deleted = 0
        for session in unnamed:
            if deleted >= to_delete:
                break
            if self.delete_session(session.session_id):
                deleted += 1

        return deleted

    # -- index management --------------------------------------------------

    def _update_index(self, meta: SessionMeta) -> None:
        """Add or update a session entry in ``index.json``."""
        index = self._load_index()
        # Replace existing entry if present.
        index = [e for e in index if e.get("session_id") != meta.session_id]
        index.append(asdict(meta))
        self._write_index(index)

    def _remove_from_index(self, session_id: str) -> None:
        """Remove a session from ``index.json``."""
        index = self._load_index()
        new_index = [e for e in index if e.get("session_id") != session_id]
        if len(new_index) != len(index):
            self._write_index(new_index)

    def _load_index(self) -> list[dict]:
        """Read ``index.json``, returning an empty list on any failure."""
        if not INDEX_PATH.exists():
            return []
        try:
            data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            log.warning("index.json is not a JSON array; resetting")
            return []
        except (json.JSONDecodeError, OSError):
            log.warning("Corrupt or unreadable index.json; resetting")
            return []

    def _write_index(self, index: list[dict]) -> None:
        """Atomically overwrite ``index.json``."""
        tmp = INDEX_PATH.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(index, ensure_ascii=False), encoding="utf-8"
            )
            tmp.replace(INDEX_PATH)
        except OSError:
            log.exception("Failed to write index.json")
            # Clean up temp file if it exists.
            tmp.unlink(missing_ok=True)

    def _refresh_meta_from_file(self, session_id: str) -> None:
        """Re-read a session file and update the index with fresh counts."""
        try:
            data = self.load_session(session_id)
        except (FileNotFoundError, ValueError):
            return

        meta: SessionMeta = data["meta"]
        messages = data["messages"]

        total_in = sum(m.get("input_tokens", 0) for m in messages)
        total_out = sum(m.get("output_tokens", 0) for m in messages)

        meta.message_count = len(messages)
        meta.total_tokens = total_in + total_out
        meta.updated_at = _now_iso()

        self._update_index(meta)
