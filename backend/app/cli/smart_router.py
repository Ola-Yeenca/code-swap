"""Smart routing engine for the code-swap CLI.

Automatically classifies user prompts by task type (code generation,
debugging, research, etc.) and routes them to the optimal model via
OpenRouter.  The classifier uses lightweight keyword matching -- no
external API calls required.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Task categories
# ---------------------------------------------------------------------------

class TaskCategory(enum.Enum):
    """High-level categories of tasks a user might request."""

    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    DEBUGGING = "debugging"
    RESEARCH = "research"
    REFACTORING = "refactoring"
    CREATIVE = "creative"
    GENERAL = "general"


# ---------------------------------------------------------------------------
# Keyword signal table
# ---------------------------------------------------------------------------

KEYWORD_SIGNALS: dict[TaskCategory, list[str]] = {
    TaskCategory.CODE_GENERATION: [
        "write", "create", "implement", "build", "add feature",
        "generate", "scaffold", "make a", "new function", "new class",
    ],
    TaskCategory.CODE_REVIEW: [
        "review", "check", "audit", "analyze code", "find bugs",
        "look at this", "what's wrong", "code quality",
    ],
    TaskCategory.DEBUGGING: [
        "fix", "debug", "error", "broken", "failing", "crash",
        "not working", "bug", "traceback", "exception",
    ],
    TaskCategory.RESEARCH: [
        "explain", "how does", "what is", "compare", "research",
        "learn about", "tell me about", "difference between",
    ],
    TaskCategory.REFACTORING: [
        "refactor", "improve", "optimize", "clean up", "simplify",
        "restructure", "reorganize", "rename",
    ],
    TaskCategory.CREATIVE: [
        "write a story", "poem", "brainstorm", "marketing",
        "name ideas", "tagline", "creative", "slogan",
    ],
}

# ---------------------------------------------------------------------------
# Default model routes  (OpenRouter model IDs)
# ---------------------------------------------------------------------------

DEFAULT_ROUTES: dict[TaskCategory, str | None] = {
    TaskCategory.CODE_GENERATION: "anthropic/claude-sonnet-4.5",
    TaskCategory.CODE_REVIEW:     "google/gemini-2.5-pro",
    TaskCategory.DEBUGGING:       "anthropic/claude-sonnet-4.5",
    TaskCategory.RESEARCH:        "deepseek/deepseek-r1",
    TaskCategory.REFACTORING:     "anthropic/claude-sonnet-4.5",
    TaskCategory.CREATIVE:        "openai/gpt-4.1",
    TaskCategory.GENERAL:         None,
}

# Confidence threshold for a category to be considered relevant.
_RELEVANCE_THRESHOLD: float = 0.1

# When 2+ categories exceed this threshold, suggest a crew run.
_CREW_SUGGEST_THRESHOLD: float = 0.3


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class TaskClassifier:
    """Classify a user prompt into task categories with confidence scores.

    Uses keyword-density matching against ``KEYWORD_SIGNALS``.  No network
    calls are made -- classification is instantaneous.
    """

    @staticmethod
    def classify(prompt: str) -> list[tuple[TaskCategory, float]]:
        """Classify *prompt* into task categories with confidence scores.

        Returns a list of ``(category, confidence)`` tuples sorted by
        confidence descending.  Only categories above the relevance
        threshold (0.1) are included.  Confidence is 0.0--1.0 based on
        keyword match density.
        """
        text = prompt.lower()
        scores: dict[TaskCategory, int] = {}

        for category, keywords in KEYWORD_SIGNALS.items():
            hits = sum(1 for kw in keywords if re.search(r"\b" + re.escape(kw), text))
            if hits:
                scores[category] = hits

        if not scores:
            return [(TaskCategory.GENERAL, 1.0)]

        max_hits = max(scores.values())
        results: list[tuple[TaskCategory, float]] = []
        for category, hits in scores.items():
            confidence = round(hits / max_hits, 2)
            if confidence >= _RELEVANCE_THRESHOLD:
                results.append((category, confidence))

        results.sort(key=lambda pair: pair[1], reverse=True)
        return results


# ---------------------------------------------------------------------------
# Routing decision
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """The outcome of routing a user prompt through the smart router."""

    model: str
    category: TaskCategory
    confidence: float
    reasoning: str
    suggest_crew: bool


# Human-friendly labels for the reasoning string.
_CATEGORY_LABELS: dict[TaskCategory, str] = {
    TaskCategory.CODE_GENERATION: "code generation",
    TaskCategory.CODE_REVIEW:     "code review",
    TaskCategory.DEBUGGING:       "debugging",
    TaskCategory.RESEARCH:        "research",
    TaskCategory.REFACTORING:     "refactoring",
    TaskCategory.CREATIVE:        "creative writing",
    TaskCategory.GENERAL:         "general",
}

# Short model names for the reasoning string.
_MODEL_SHORT_NAMES: dict[str, str] = {
    "anthropic/claude-sonnet-4-5": "Claude Sonnet 4.5",
    "google/gemini-2.5-pro":      "Gemini 2.5 Pro",
    "deepseek/deepseek-r1":       "DeepSeek R1",
    "openai/gpt-4.1":             "GPT-4.1",
}


# ---------------------------------------------------------------------------
# Smart router
# ---------------------------------------------------------------------------

class SmartRouter:
    """Route user prompts to the best model based on task classification.

    Parameters
    ----------
    default_model:
        Fallback model when no category matches or the category maps to
        ``None``.
    route_overrides:
        Optional user-supplied mapping of ``TaskCategory.value`` strings
        to model IDs.  Overrides take precedence over ``DEFAULT_ROUTES``.
    """

    def __init__(
        self,
        default_model: str,
        route_overrides: dict[str, str] | None = None,
    ) -> None:
        self._default_model = default_model
        self._overrides: dict[str, str] = route_overrides or {}

    # -- public API --------------------------------------------------------

    def route(self, prompt: str) -> RoutingDecision:
        """Classify *prompt* and return a ``RoutingDecision``."""
        ranked = TaskClassifier.classify(prompt)
        top_category, top_confidence = ranked[0]

        model = self._resolve_model(top_category)

        # Suggest a crew when multiple categories are strong signals.
        strong = [cat for cat, conf in ranked if conf >= _CREW_SUGGEST_THRESHOLD]
        suggest_crew = len(strong) >= 2

        label = _CATEGORY_LABELS.get(top_category, top_category.value)
        short = _MODEL_SHORT_NAMES.get(model, model.split("/")[-1])
        reasoning = f"Detected {label} task \u2192 routing to {short}"

        return RoutingDecision(
            model=model,
            category=top_category,
            confidence=top_confidence,
            reasoning=reasoning,
            suggest_crew=suggest_crew,
        )

    def get_route_table(self) -> dict[str, str]:
        """Return the effective route table (defaults merged with overrides).

        Keys are ``TaskCategory.value`` strings; values are model IDs.
        Used by the ``/route`` command to display current routing config.
        """
        table: dict[str, str] = {}
        for cat in TaskCategory:
            table[cat.value] = self._resolve_model(cat)
        return table

    # -- internal ----------------------------------------------------------

    def _resolve_model(self, category: TaskCategory) -> str:
        """Pick the model for *category*.

        Resolution order: user overrides -> DEFAULT_ROUTES -> default_model.
        """
        # 1. User override
        override = self._overrides.get(category.value)
        if override:
            return override

        # 2. Built-in default route
        default = DEFAULT_ROUTES.get(category)
        if default is not None:
            return default

        # 3. Fallback
        return self._default_model
