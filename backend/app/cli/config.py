"""Configuration for the code-swap CLI.

OpenRouter is the sole transport layer. Every model (OpenAI, Anthropic, Google,
Meta, etc.) is accessed through OpenRouter with a single API key.

Resolution chains
-----------------
API key:  CLI flag  ->  env var OPENROUTER_API_KEY  ->  config file ``api_key``
Model:    CLI flag  ->  config file ``model``        ->  DEFAULT_MODEL
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Paths & defaults
# ---------------------------------------------------------------------------

CONFIG_PATH: Path = Path.home() / ".code_swap.yaml"

DEFAULT_MODEL: str = "anthropic/claude-sonnet-4.5"

ENV_VAR: str = "OPENROUTER_API_KEY"

OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

# ---------------------------------------------------------------------------
# Pricing table  (cost per 1 M tokens, USD)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Input and output cost per million tokens in USD."""
    input: float
    output: float


# Hardcoded for popular models. Falls back to "unknown" for unlisted ones.
_PRICING_TABLE: dict[str, ModelPricing] = {
    "anthropic/claude-opus-4.6":         ModelPricing(input=15.00, output=75.00),
    "anthropic/claude-opus-4.5":         ModelPricing(input=15.00, output=75.00),
    "anthropic/claude-sonnet-4.5":       ModelPricing(input=3.00,  output=15.00),
    "anthropic/claude-haiku-4.5":        ModelPricing(input=0.80,  output=4.00),
    "anthropic/claude-3.5-haiku":        ModelPricing(input=0.80,  output=4.00),
    # OpenAI
    "openai/gpt-5":                      ModelPricing(input=2.50,  output=10.00),
    "openai/gpt-4.1":                    ModelPricing(input=2.00,  output=8.00),
    "openai/gpt-4.1-mini":              ModelPricing(input=0.40,  output=1.60),
    "openai/gpt-4.1-nano":              ModelPricing(input=0.10,  output=0.40),
    "openai/o3":                         ModelPricing(input=10.00, output=40.00),
    "openai/o4-mini":                    ModelPricing(input=1.10,  output=4.40),
    # Google
    "google/gemini-2.5-pro":             ModelPricing(input=1.25,  output=10.00),
    "google/gemini-2.5-flash":           ModelPricing(input=0.15,  output=0.60),
    "google/gemini-2.0-flash":           ModelPricing(input=0.10,  output=0.40),
    # Meta
    "meta-llama/llama-4-maverick":       ModelPricing(input=0.50,  output=0.70),
    "meta-llama/llama-4-scout":          ModelPricing(input=0.15,  output=0.40),
    # DeepSeek
    "deepseek/deepseek-r1":              ModelPricing(input=0.55,  output=2.19),
    "deepseek/deepseek-chat-v3-0324":    ModelPricing(input=0.27,  output=1.10),
    # Mistral
    "mistralai/mistral-large":           ModelPricing(input=2.00,  output=6.00),
    "mistralai/mistral-small":           ModelPricing(input=0.10,  output=0.30),
}


def get_model_pricing(model_id: str) -> ModelPricing | None:
    """Return estimated pricing for *model_id*, or ``None`` if unknown."""
    return _PRICING_TABLE.get(model_id)


# ---------------------------------------------------------------------------
# Config file I/O
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class AppConfig:
    """In-memory representation of ~/.code_swap.yaml."""
    api_key: str | None = None
    model: str = DEFAULT_MODEL
    model_selected: bool = False  # True once user explicitly picks a model
    auto_save: bool = True
    theme: str = "dark"
    auto_resume: bool = False
    max_sessions: int = 50
    yolo_mode: bool = False
    auto_route: bool = False
    route_overrides: dict[str, str] | None = None


def load_config() -> AppConfig:
    """Read the config file and return an ``AppConfig``.

    Missing keys silently fall back to defaults.  If the file does not
    exist or is unparseable, a default config is returned.
    """
    if not CONFIG_PATH.exists():
        return AppConfig()
    try:
        raw: dict[str, Any] = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    except Exception:
        return AppConfig()

    return AppConfig(
        api_key=raw.get("api_key"),
        model=raw.get("model", DEFAULT_MODEL),
        model_selected=raw.get("model_selected", False),
        auto_save=raw.get("auto_save", True),
        theme=raw.get("theme", "dark"),
        auto_resume=raw.get("auto_resume", False),
        max_sessions=raw.get("max_sessions", 50),
        yolo_mode=raw.get("yolo_mode", False),
        auto_route=raw.get("auto_route", False),
        route_overrides=raw.get("route_overrides"),
    )


def save_config(cfg: AppConfig) -> Path:
    """Persist *cfg* to the config file.  Returns the path written."""
    data: dict[str, Any] = {
        "model": cfg.model,
        "model_selected": cfg.model_selected,
        "auto_save": cfg.auto_save,
        "theme": cfg.theme,
        "auto_resume": cfg.auto_resume,
        "max_sessions": cfg.max_sessions,
        "yolo_mode": cfg.yolo_mode,
    }
    # Only write the key if set (avoid writing None)
    if cfg.api_key:
        data["api_key"] = cfg.api_key
    data["auto_route"] = cfg.auto_route
    if cfg.route_overrides:
        data["route_overrides"] = cfg.route_overrides

    CONFIG_PATH.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    return CONFIG_PATH


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------

def is_model_configured() -> bool:
    """Check whether the user has explicitly chosen a model.

    Returns ``False`` when the ``model_selected`` flag is not set —
    meaning the user has never actively picked a preferred model through
    the first-run picker or ``config --model`` and should be prompted.
    """
    if not CONFIG_PATH.exists():
        return False
    try:
        raw: dict[str, Any] = yaml.safe_load(CONFIG_PATH.read_text()) or {}
    except Exception:
        return False
    return raw.get("model_selected", False) is True


def resolve_api_key(cli_key: str | None = None) -> str:
    """Resolve the OpenRouter API key.

    Priority: *cli_key* -> ``OPENROUTER_API_KEY`` env var -> config file.
    Raises ``SystemExit`` with a helpful message when no key is found.
    """
    if cli_key:
        return cli_key

    env_val = os.environ.get(ENV_VAR)
    if env_val:
        return env_val

    cfg = load_config()
    if cfg.api_key:
        return cfg.api_key

    raise SystemExit(
        f"No API key found.  Provide one of:\n"
        f"  1. Pass --api-key on the command line\n"
        f"  2. Set the {ENV_VAR} environment variable\n"
        f"  3. Add 'api_key: sk-or-v1-...' to {CONFIG_PATH}\n"
        f"\n"
        f"Get a key at https://openrouter.ai/keys"
    )


def resolve_model(cli_model: str | None = None) -> str:
    """Resolve the model to use.

    Priority: *cli_model* -> config file ``model`` -> ``DEFAULT_MODEL``.
    """
    if cli_model:
        return cli_model

    cfg = load_config()
    return cfg.model  # already defaults to DEFAULT_MODEL


# ---------------------------------------------------------------------------
# First-run setup
# ---------------------------------------------------------------------------

def ensure_setup() -> bool:
    """Check that a usable API key exists.

    If no key is found anywhere in the resolution chain, print a
    friendly first-run message and return ``False``.  Otherwise
    return ``True`` silently.
    """
    try:
        resolve_api_key()
        return True
    except SystemExit:
        pass

    print(
        "\n"
        "  Welcome to code-swap!\n"
        "  ---------------------\n"
        "\n"
        "  code-swap uses OpenRouter to access every major AI model\n"
        "  (OpenAI, Anthropic, Google, Meta, and more) with one API key.\n"
        "\n"
        "  Quick setup:\n"
        "\n"
        "    1. Get a free API key at https://openrouter.ai/keys\n"
        "    2. Then pick ONE of these options:\n"
        "\n"
        f"       export {ENV_VAR}=sk-or-v1-...\n"
        "\n"
        "       -- or --\n"
        "\n"
        f"       echo 'api_key: sk-or-v1-...' > {CONFIG_PATH}\n"
        "\n"
        "  That's it. Run 'code-swap --help' to get started.\n",
        file=sys.stderr,
    )
    return False
