"""Interactive fuzzy-search model picker for the AI CLI tool.

Queries the OpenRouter model catalog and presents a fuzzy finder with
popular models surfaced first, grouped by provider.
"""

from __future__ import annotations

import httpx
from InquirerPy import inquirer

POPULAR_MODEL_IDS: list[str] = [
    "anthropic/claude-opus-4-6",
    "anthropic/claude-sonnet-4-5",
    "anthropic/claude-haiku-4-5",
    "openai/gpt-5",
    "openai/gpt-4.1",
    "openai/gpt-4.1-mini",
    "openai/o3",
    "openai/o4-mini",
    "google/gemini-2.5-pro",
    "google/gemini-2.5-flash",
    "google/gemini-2.0-flash",
    "deepseek/deepseek-r1",
    "deepseek/deepseek-chat-v3-0324",
    "meta-llama/llama-4-maverick",
    "meta-llama/llama-4-scout",
    "mistralai/mistral-large",
    "mistralai/mistral-small",
]

_POPULAR_SET = set(POPULAR_MODEL_IDS)

_POPULAR_RANK = {model_id: i for i, model_id in enumerate(POPULAR_MODEL_IDS)}


def _format_price(price_per_token: str) -> str:
    val = float(price_per_token)
    if val == 0:
        return "free"
    per_million = val * 1_000_000
    if per_million >= 1:
        return f"${per_million:.1f}/M"
    return f"${per_million:.2f}/M"


def _format_context(ctx: int) -> str:
    if ctx >= 1_000_000:
        return f"{ctx // 1_000_000}M"
    if ctx >= 1_000:
        return f"{ctx // 1_000}k"
    return str(ctx)


async def fetch_models(api_key: str) -> list[dict]:
    """Fetch models from OpenRouter.

    Returns a list sorted with popular models first, then the rest
    alphabetically.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()

    data: list[dict] = resp.json()["data"]

    models = [
        {
            "id": m["id"],
            "name": m.get("name", m["id"]),
            "context_length": m.get("context_length", 0),
            "pricing": {
                "prompt": m.get("pricing", {}).get("prompt", "0"),
                "completion": m.get("pricing", {}).get("completion", "0"),
            },
            "is_popular": m["id"] in _POPULAR_SET,
        }
        for m in data
    ]

    def sort_key(m: dict) -> tuple[int, int, str]:
        if m["is_popular"]:
            return (0, _POPULAR_RANK.get(m["id"], 999), m["id"])
        return (1, 0, m["id"])

    models.sort(key=sort_key)
    return models


def _build_picker(models: list[dict], current_model: str | None):
    """Build the InquirerPy fuzzy selector with popular models first."""
    choices = []
    default: str | None = None
    seen_other = False

    for m in models:
        ctx = _format_context(m.get("context_length", 0))
        prompt_price = _format_price(m.get("pricing", {}).get("prompt", "0"))

        if m.get("is_popular"):
            label = f"\u2605 {m['id']}  ({ctx} ctx, {prompt_price})"
        else:
            if not seen_other:
                choices.append({"name": "\u2500\u2500\u2500 all models \u2500\u2500\u2500", "value": None})
                seen_other = True
            label = f"  {m['id']}  ({ctx} ctx, {prompt_price})"

        choices.append({"name": label, "value": m["id"]})

        if current_model and m["id"] == current_model:
            default = label

    from InquirerPy.utils import get_style

    custom_style = get_style({
        "questionmark": "#458af7",
        "pointer": "#00ff87",
        "marker": "#ffd700",
        "answered_question": "#6a6a8a",
        "input": "#458af7",
        "question": "bold #ffffff",
        "answered_input": "#6a6a8a",
    }, style_override=False)

    return inquirer.fuzzy(
        message="Pick your model (type to search):",
        choices=choices,
        default=default,
        match_exact=False,
        mandatory=True,
        style=custom_style,
        pointer="\u25c8 ",
    )


def pick_model(models: list[dict], current_model: str | None = None) -> str:
    """Show a fuzzy picker and return selected model ID (sync version)."""
    picker = _build_picker(models, current_model)
    result: str = picker.execute()
    return result


async def pick_model_async(models: list[dict], current_model: str | None = None) -> str:
    """Show a fuzzy picker and return selected model ID (async-safe version)."""
    picker = _build_picker(models, current_model)
    result: str = await picker.execute_async()
    return result
