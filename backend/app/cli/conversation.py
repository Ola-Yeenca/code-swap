"""Multi-turn conversation state and token tracking for the code-swap CLI.

Manages message history in OpenAI-compatible chat/completions format
for use with OpenRouter as the transport layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time


# ---------------------------------------------------------------------------
# Default system prompt
# ---------------------------------------------------------------------------

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful coding assistant accessed via the code-swap CLI tool. "
    "Be concise, provide code examples when relevant, and format responses in markdown."
)


# ---------------------------------------------------------------------------
# Model pricing (per million tokens, USD)
# ---------------------------------------------------------------------------

# Import the canonical pricing table from config to avoid duplication.
from app.cli.config import get_model_pricing as _get_config_pricing

# Fallback rate for models not in the pricing table (per million tokens, USD).
_DEFAULT_INPUT_RATE = 1.0
_DEFAULT_OUTPUT_RATE = 5.0


def _get_pricing(model: str) -> dict[str, float]:
    """Return pricing dict for *model*, falling back to defaults."""
    p = _get_config_pricing(model)
    if p is not None:
        return {"input": p.input, "output": p.output}
    return {"input": _DEFAULT_INPUT_RATE, "output": _DEFAULT_OUTPUT_RATE}


# ---------------------------------------------------------------------------
# Message type
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Message:
    """A single message in the conversation."""

    role: str  # "system" | "user" | "assistant"
    content: str

    def to_dict(self) -> dict[str, str]:
        """Serialize to OpenAI chat/completions format."""
        return {"role": self.role, "content": self.content}


# ---------------------------------------------------------------------------
# TokenTracker
# ---------------------------------------------------------------------------

@dataclass
class RequestRecord:
    """One recorded API round-trip."""

    input_tokens: int
    output_tokens: int
    model: str
    cost: float
    timestamp: float


@dataclass
class TokenTracker:
    """Track token usage and estimated cost across an entire CLI session."""

    _requests: list[RequestRecord] = field(default_factory=list)

    # -- recording --------------------------------------------------------

    def record_request(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str,
    ) -> None:
        """Record a completed API request."""
        cost = self.estimate_cost(input_tokens, output_tokens, model)
        self._requests.append(
            RequestRecord(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model,
                cost=cost,
                timestamp=time(),
            )
        )

    # -- cost estimation --------------------------------------------------

    @staticmethod
    def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
        """Estimate USD cost for a single request."""
        pricing = _get_pricing(model)
        return (
            input_tokens * pricing["input"] / 1_000_000
            + output_tokens * pricing["output"] / 1_000_000
        )

    # -- session-level aggregates -----------------------------------------

    @property
    def session_input_tokens(self) -> int:
        return sum(r.input_tokens for r in self._requests)

    @property
    def session_output_tokens(self) -> int:
        return sum(r.output_tokens for r in self._requests)

    @property
    def total_tokens(self) -> int:
        return self.session_input_tokens + self.session_output_tokens

    @property
    def session_cost(self) -> float:
        return sum(r.cost for r in self._requests)

    @property
    def request_count(self) -> int:
        return len(self._requests)

    # -- formatting -------------------------------------------------------

    def format_stats(self) -> str:
        """Human-readable one-liner for the status bar.

        Example: "Session: 12,345 tokens / $0.0523 (3 requests)"
        """
        return (
            f"Session: {self.total_tokens:,} tokens / "
            f"${self.session_cost:.4f} ({self.request_count} requests)"
        )

    def format_last_request(self) -> str:
        """Human-readable summary of the most recent request."""
        if not self._requests:
            return ""
        last = self._requests[-1]
        return (
            f"[{last.input_tokens:,} in / {last.output_tokens:,} out"
            f" ~ ${last.cost:.4f}]"
        )


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------

@dataclass
class Conversation:
    """Manages multi-turn message history in OpenAI chat/completions format.

    Usage::

        conv = Conversation()
        conv.add_user_message("Explain asyncio")
        messages = conv.get_messages()
        # -> [{"role": "system", ...}, {"role": "user", "content": "Explain asyncio"}]
    """

    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    _messages: list[Message] = field(default_factory=list)
    _files: set[str] = field(default_factory=set)
    _tracker: TokenTracker = field(default_factory=TokenTracker)

    def __post_init__(self) -> None:
        # Materialise the system message so it is always at index 0.
        if self.system_prompt:
            self._messages.insert(0, Message(role="system", content=self.system_prompt))

    # -- mutators ---------------------------------------------------------

    def add_user_message(self, content: str) -> None:
        """Append a user message to the history."""
        self._messages.append(Message(role="user", content=content))

    def add_assistant_message(self, content: str) -> None:
        """Append an assistant response to the history."""
        self._messages.append(Message(role="assistant", content=content))

    def add_file_context(self, filename: str, content: str) -> None:
        """Inject a file's contents as a labelled user message.

        Called when the user references a file via ``@filename`` in the REPL.
        The content is wrapped so the model can clearly identify it.
        """
        wrapped = (
            f"<file path=\"{filename}\">\n"
            f"{content}\n"
            f"</file>"
        )
        self._messages.append(Message(role="user", content=wrapped))
        self._files.add(filename)

    def remove_last_message(self) -> None:
        """Remove the most recently added message (for error recovery)."""
        if self._messages and self._messages[-1].role != "system":
            self._messages.pop()

    def clear(self) -> None:
        """Reset conversation history, keeping the system prompt."""
        self._messages.clear()
        self._files.clear()
        if self.system_prompt:
            self._messages.insert(0, Message(role="system", content=self.system_prompt))

    # -- serialisation ----------------------------------------------------

    def get_messages(self) -> list[dict[str, str]]:
        """Return the full message list in OpenAI chat/completions format."""
        return [m.to_dict() for m in self._messages]

    # -- introspection ----------------------------------------------------

    @property
    def message_count(self) -> int:
        """Number of messages excluding the system prompt."""
        return sum(1 for m in self._messages if m.role != "system")

    @property
    def estimated_tokens(self) -> int:
        """Rough token estimate for the current conversation context.

        Uses the widely-accepted heuristic of ~4 characters per token.
        """
        total_chars = sum(len(m.content) for m in self._messages)
        return total_chars // 4

    @property
    def tracker(self) -> TokenTracker:
        """Access the session's token tracker."""
        return self._tracker

    @property
    def referenced_files(self) -> list[str]:
        """Return a sorted list of all unique file paths injected into history."""
        return sorted(list(self._files))

    # -- convenience helpers ----------------------------------------------

    @property
    def last_assistant_message(self) -> str | None:
        """Return the most recent assistant response, or None."""
        for m in reversed(self._messages):
            if m.role == "assistant":
                return m.content
        return None

    def set_system_prompt(self, prompt: str) -> None:
        """Replace the system prompt (updates the first message in-place)."""
        self.system_prompt = prompt
        if self._messages and self._messages[0].role == "system":
            self._messages[0] = Message(role="system", content=prompt)
        else:
            self._messages.insert(0, Message(role="system", content=prompt))

    # -- persistence ----------------------------------------------------------

    def to_serializable(self) -> dict:
        """Export conversation state for persistence.

        Returns dict with keys: system_prompt, messages (list of dicts with role, content),
        tracker_records (list of dicts with input_tokens, output_tokens, model, cost, timestamp).
        """
        return {
            "system_prompt": self.system_prompt,
            "messages": [
                {"role": m.role, "content": m.content}
                for m in self._messages
                if m.role != "system"  # system prompt stored separately
            ],
            "tracker_records": [
                {
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "model": r.model,
                    "cost": r.cost,
                    "timestamp": r.timestamp,
                }
                for r in self._tracker._requests
            ],
        }

    @classmethod
    def from_serializable(cls, data: dict) -> "Conversation":
        """Reconstruct a Conversation from serialized data."""
        conv = cls(system_prompt=data.get("system_prompt", DEFAULT_SYSTEM_PROMPT))
        for msg in data.get("messages", []):
            conv._messages.append(Message(role=msg["role"], content=msg["content"]))
        for rec in data.get("tracker_records", []):
            conv._tracker._requests.append(
                RequestRecord(
                    input_tokens=rec["input_tokens"],
                    output_tokens=rec["output_tokens"],
                    model=rec["model"],
                    cost=rec["cost"],
                    timestamp=rec["timestamp"],
                )
            )
        return conv
