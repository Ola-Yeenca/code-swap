"""code-swap CLI entry point.

REPL-first design:
    code-swap              -> launch interactive REPL
    code-swap ask "prompt" -> one-shot query
    code-swap models       -> list available models
    code-swap config       -> manage API key and settings

All model access goes through OpenRouter as the transport layer.
"""

from __future__ import annotations

import asyncio
import json
import os

import click

# Ensure minimal env so pydantic-settings doesn't blow up for CLI usage.
os.environ.setdefault("DATABASE_URL", "sqlite:///unused.db")
os.environ.setdefault("SESSION_SECRET", "cli-placeholder-secret")

from app.cli.config import (  # noqa: E402
    CONFIG_PATH,
    OPENROUTER_BASE_URL,
    ensure_setup,
    load_config,
    resolve_api_key,
    resolve_model,
    save_config,
)
from app.cli import output as out  # noqa: E402


# ---------------------------------------------------------------------------
# One-shot streaming helper
# ---------------------------------------------------------------------------

async def _oneshot(api_key: str, model: str, prompt: str) -> None:
    """Run a single prompt through OpenRouter and stream to the terminal."""
    import httpx

    # 1. Reasoning Phase
    reasoning = out.ReasoningDisplay()
    reasoning.start(f"Analyzing with {model}...")

    # 2. Streaming Phase
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/code-swap",
        "X-Title": "code-swap",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    display = out.StreamingDisplay()
    input_tokens = 0
    output_tokens = 0

    try:
        tokens_started = False
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=body,
            ) as response:
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

                    if not tokens_started:
                        reasoning.stop()
                        display.start()
                        tokens_started = True

                    choices = event.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        text = delta.get("content")
                        if text:
                            display.token(text)

                    usage = event.get("usage")
                    if usage:
                        input_tokens = usage.get("prompt_tokens", 0)
                        output_tokens = usage.get("completion_tokens", 0)

        display.finish()

        # Estimate if API didn't return usage
        result = display.text
        if not output_tokens:
            output_tokens = max(1, len(result) // 4)

        from app.cli.conversation import TokenTracker
        cost = TokenTracker.estimate_cost(input_tokens, output_tokens, model)

        out.print_response_footer(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            elapsed=display.elapsed,
        )

        # Auto-save
        path = out.save_result("ask", f"# Ask ({model})\n\n**Prompt:** {prompt}\n\n{result}")
        out.print_saved(path)

    except httpx.HTTPStatusError as exc:
        display.finish()
        out.print_error(
            f"API error: {exc.response.status_code}",
            detail=exc.response.text[:200] if exc.response.text else None,
            suggestion="Check your API key and model ID",
        )
    except Exception as exc:  # noqa: BLE001
        display.finish()
        out.print_error(f"Request failed: {exc}")


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group(invoke_without_command=True)
@click.version_option(version=out.VERSION, prog_name="code-swap")
@click.option("--model", "-m", default=None, help="Model ID (OpenRouter format)")
@click.option("--api-key", default=None, help="OpenRouter API key")
@click.option("--yolo", is_flag=True, default=False, help="Auto-approve all tool executions")
@click.pass_context
def cli(ctx: click.Context, model: str | None, api_key: str | None, yolo: bool) -> None:
    """code-swap: BYOK AI CLI powered by OpenRouter.

    Run without arguments to start an interactive REPL session.
    """
    # Store resolved values for subcommands
    ctx.ensure_object(dict)
    ctx.obj["model_override"] = model
    ctx.obj["key_override"] = api_key
    ctx.obj["yolo"] = yolo

    if ctx.invoked_subcommand is not None:
        return

    # Default action: launch REPL
    if not ensure_setup():
        raise SystemExit(1)

    api_key_resolved = resolve_api_key(api_key)
    model_resolved = resolve_model(model)

    out.print_banner(model=model_resolved, key_set=True)

    from app.cli.repl import Repl

    repl = Repl(
        api_key=api_key_resolved,
        default_model=model_resolved,
        output=out,
        yolo_mode=yolo,
    )
    asyncio.run(repl.run())


# ---------------------------------------------------------------------------
# ask: one-shot prompt
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("prompt")
@click.option("--model", "-m", default=None, help="Model ID (OpenRouter format)")
@click.option("--api-key", default=None, help="OpenRouter API key")
def ask(prompt: str, model: str | None, api_key: str | None) -> None:
    """Send a one-shot prompt and print the response."""
    api_key_resolved = resolve_api_key(api_key)
    model_resolved = resolve_model(model)

    out.print_banner(model=model_resolved, key_set=True)
    asyncio.run(_oneshot(api_key_resolved, model_resolved, prompt))


# ---------------------------------------------------------------------------
# models: list available models
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--api-key", default=None, help="OpenRouter API key")
@click.option("--search", "-s", default=None, help="Filter models by name/ID")
def models(api_key: str | None, search: str | None) -> None:
    """List available models from OpenRouter."""
    from rich.table import Table

    api_key_resolved = resolve_api_key(api_key)

    async def fetch() -> list[dict]:
        from app.cli.picker import fetch_models
        return await fetch_models(api_key_resolved)

    out.console.print("[muted]Fetching models from OpenRouter...[/]")
    model_list = asyncio.run(fetch())

    if search:
        search_lower = search.lower()
        model_list = [m for m in model_list if search_lower in m["id"].lower() or search_lower in m.get("name", "").lower()]

    table = Table(
        title="Available Models",
        show_lines=False,
        border_style="dim",
        title_style="bold",
        header_style="bold dim",
    )
    table.add_column("Model ID", style="cyan", min_width=35)
    table.add_column("Context", justify="right", width=10)
    table.add_column("$/M Input", justify="right", width=10, style="green")
    table.add_column("$/M Output", justify="right", width=10, style="green")

    for m in model_list:
        ctx = m.get("context_length", 0)
        pricing = m.get("pricing", {})
        prompt_price = pricing.get("prompt", "0")
        completion_price = pricing.get("completion", "0")

        ctx_str = f"{ctx:,}" if ctx else "-"

        table.add_row(
            m["id"],
            ctx_str,
            f"${float(prompt_price) * 1_000_000:.2f}" if prompt_price != "0" else "free",
            f"${float(completion_price) * 1_000_000:.2f}" if completion_price != "0" else "free",
        )

    out.console.print()
    out.console.print(table)
    out.console.print(f"\n[muted]{len(model_list)} models found[/]")


# ---------------------------------------------------------------------------
# config: manage settings
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--key", default=None, help="Set your OpenRouter API key")
@click.option("--model", "-m", default=None, help="Set the default model")
@click.option("--show", is_flag=True, help="Show current configuration")
def config(key: str | None, model: str | None, show: bool) -> None:
    """Manage code-swap configuration."""
    cfg = load_config()

    if show or (key is None and model is None):
        out.console.print("[accent]Current configuration[/]")
        out.console.print(f"  [muted]Config file:[/] {CONFIG_PATH}")
        if cfg.api_key and len(cfg.api_key) > 16:
            key_display = f"{cfg.api_key[:12]}...{cfg.api_key[-4:]}"
        elif cfg.api_key:
            key_display = "[redacted]"
        else:
            key_display = "[error]not set[/]"
        out.console.print(f"  [muted]API key:[/]     {key_display}")
        out.console.print(f"  [muted]Model:[/]       [cyan]{cfg.model}[/]")
        out.console.print(f"  [muted]Auto-save:[/]   {cfg.auto_save}")

        if not cfg.api_key:
            out.console.print()
            out.print_error(
                "API key not configured",
                suggestion="Run: code-swap config --key sk-or-v1-YOUR_KEY",
            )
        return

    if key is not None:
        cfg.api_key = key
    if model is not None:
        cfg.model = model

    path = save_config(cfg)
    out.print_success(f"Configuration saved to {path}")

    if key is not None:
        out.console.print(f"  [muted]API key:[/] {key[:12]}...{key[-4:]}")
    if model is not None:
        out.console.print(f"  [muted]Model:[/]   [cyan]{model}[/]")


# ---------------------------------------------------------------------------
# install: native installer
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--method",
    type=click.Choice(["auto", "uv", "pipx", "pip"]),
    default="auto",
    help="Install method (default: auto-detect best available)",
)
def install(method: str) -> None:
    """Install code-swap globally so it works from any directory."""
    from app.cli.installer import install_pipeline

    success = install_pipeline(preference=method)
    if not success:
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# run: multi-model agent crew
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("task")
@click.option("--crew", "-c", default="default", help="Crew configuration name")
@click.option("--model", "-m", default=None, help="Model ID for default crew")
@click.option("--api-key", default=None, help="OpenRouter API key")
@click.option("--budget", "-b", default=5.0, type=float, help="Budget limit in USD")
def run(task: str, crew: str, model: str | None, api_key: str | None, budget: float) -> None:
    """Run a task with a multi-model agent crew.

    Example: code-swap run "Implement JWT auth" --crew full-stack
    """
    api_key_resolved = resolve_api_key(api_key)

    from app.cli.crew import load_crew, ensure_default_crews
    from app.cli.engine import CrewEngine
    from app.cli.crew_display import CrewDisplay

    ensure_default_crews()

    try:
        crew_config = load_crew(crew)
    except Exception as exc:
        out.print_error(f"Failed to load crew '{crew}': {exc}")
        raise SystemExit(1)

    crew_config.budget_limit_usd = budget

    out.print_banner(model=crew_config.orchestrator, key_set=True)
    out.console.print(f"[muted]Running crew: {crew_config.name} ({len(crew_config.agents)} agents)[/]")
    out.console.print(f"[muted]Task: {task}[/]")
    out.console.print()

    async def _run():
        queue: asyncio.Queue = asyncio.Queue()

        async def on_event(event: dict):
            await queue.put(event)

        engine = CrewEngine(
            api_key=api_key_resolved,
            crew=crew_config,
            on_event=on_event,
        )

        display = CrewDisplay(
            crew_name=crew_config.name,
            task=task,
            budget=crew_config.budget_limit_usd,
        )

        # Run engine and display concurrently
        engine_task = asyncio.create_task(engine.execute(task))
        await display.run(queue)
        result = await engine_task

        return result

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
