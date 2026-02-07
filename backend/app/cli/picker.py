"""Interactive fuzzy-search model picker for the AI CLI tool.

Queries the OpenRouter model catalog and presents a beautiful fuzzy finder
so users can browse and search available models.
"""

from __future__ import annotations

import httpx
from InquirerPy import inquirer


async def fetch_models(api_key: str) -> list[dict]:
    """Fetch models from OpenRouter.

    Returns a sorted list of dicts with keys:
    ``id``, ``name``, ``context_length``, and ``pricing``.
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
        }
        for m in data
    ]

    models.sort(key=lambda m: m["id"])
    return models


def _build_picker(models: list[dict], current_model: str | None):
    """Build the InquirerPy fuzzy selector object."""
    choices = []
    default: str | None = None

    for m in models:
        ctx = m.get("context_length", 0)
        prompt_price = m.get("pricing", {}).get("prompt", "0")
        label = f"{m['id']}  (ctx: {ctx}, ${prompt_price}/tok)"
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
        message="Select intelligence profile:",
        choices=choices,
        default=default,
        match_exact=False,
        mandatory=True,
        style=custom_style,
        pointer="\u25c8 ",  # Modern diamond pointer
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
