"""Multi-model crew orchestration engine.

Executes a three-phase workflow:

1. **Planning** -- the orchestrator agent breaks the user's task into subtasks
   and assigns each to a specialist agent.
2. **Execution** -- subtasks are dispatched in parallel (bounded by a
   semaphore) to their assigned agents via OpenRouter streaming.
3. **Synthesis** -- the orchestrator merges all subtask results into a single
   coherent response.

Events are pushed to the caller through an async callback (``on_event``) so
that the REPL / UI can update in real time.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

from app.cli.config import OPENROUTER_BASE_URL, get_model_pricing
from app.cli.crew import AgentDef, CrewConfig

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Subtask:
    """A single unit of work produced by the planning phase."""

    id: str
    description: str
    assigned_to: str
    status: str = "pending"  # pending | running | done | failed
    result: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class CrewRun:
    """Tracks the state of a complete crew execution."""

    run_id: str
    crew: CrewConfig
    user_task: str
    subtasks: list[Subtask] = field(default_factory=list)
    status: str = "planning"  # planning | executing | synthesizing | done | failed
    final_result: str = ""
    start_time: float = field(default_factory=time.monotonic)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CrewEngine:
    """Orchestrate multi-model crew execution.

    Parameters
    ----------
    api_key:
        OpenRouter API key.
    crew:
        The crew configuration describing agents and budget.
    on_event:
        Async callback invoked with structured event dicts so the caller can
        render progress in real time.
    """

    def __init__(
        self,
        api_key: str,
        crew: CrewConfig,
        on_event: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self._api_key = api_key
        self._crew = crew
        self._on_event = on_event
        self._total_cost = 0.0

    # -- public API ---------------------------------------------------------

    async def execute(self, user_task: str) -> CrewRun:
        """Run the full plan -> execute -> synthesize pipeline.

        Returns a ``CrewRun`` with the final result and per-subtask metadata.
        """
        run = CrewRun(
            run_id=uuid.uuid4().hex[:12],
            crew=self._crew,
            user_task=user_task,
        )

        await self._on_event(
            {
                "type": "crew_start",
                "sessionId": run.run_id,
                "agents": list(self._crew.agents.keys()),
            }
        )

        try:
            # Phase 1 -- Planning
            run.status = "planning"
            orchestrator = self._crew.agents[self._crew.orchestrator]
            subtasks = await self._plan(orchestrator, user_task, run)
            run.subtasks = subtasks

            await self._on_event(
                {
                    "type": "plan",
                    "subtasks": [
                        {
                            "id": s.id,
                            "description": s.description,
                            "assignTo": s.assigned_to,
                        }
                        for s in subtasks
                    ],
                }
            )

            # Phase 2 -- Parallel execution (semaphore-bounded)
            run.status = "executing"
            sem = asyncio.Semaphore(3)

            async def _run_subtask(subtask: Subtask) -> None:
                async with sem:
                    await self._execute_subtask(subtask, run)

            await asyncio.gather(*[_run_subtask(s) for s in subtasks])

            # Phase 3 -- Synthesis
            run.status = "synthesizing"
            final = await self._synthesize(orchestrator, run)
            run.final_result = final
            run.status = "done"

        except Exception as exc:
            run.status = "failed"
            run.final_result = f"Crew execution failed: {exc}"
            await self._on_event({"type": "error", "message": str(exc)})

        return run

    # -- Phase 1: Planning --------------------------------------------------

    async def _plan(
        self,
        orchestrator: AgentDef,
        user_task: str,
        run: CrewRun,
    ) -> list[Subtask]:
        """Ask the orchestrator to decompose *user_task* into subtasks."""
        specialist_names = [
            name
            for name, agent in self._crew.agents.items()
            if agent.role == "specialist"
        ]

        messages = [
            {"role": "system", "content": orchestrator.system_prompt},
            {
                "role": "user",
                "content": (
                    f"Break this task into subtasks and assign each to one of "
                    f"these agents: {', '.join(specialist_names)}\n\n"
                    f"Task: {user_task}\n\n"
                    f"Respond with JSON only: "
                    f'{{"subtasks": [{{"id": "1", "description": "...", '
                    f'"assign_to": "agent_name"}}]}}'
                ),
            },
        ]

        text, in_tok, out_tok = await self._call_model(
            orchestrator.model, messages, orchestrator.max_tokens
        )

        cost = self._estimate_cost(in_tok, out_tok, orchestrator.model)
        self._total_cost += cost

        return self._parse_plan(text, specialist_names, user_task)

    def _parse_plan(
        self,
        text: str,
        specialist_names: list[str],
        user_task: str,
    ) -> list[Subtask]:
        """Parse the orchestrator's JSON plan into ``Subtask`` objects.

        Gracefully handles markdown-fenced JSON, partial JSON, or total
        failure (falls back to a single subtask).
        """
        json_text = text
        if "```json" in text:
            json_text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            json_text = text.split("```")[1].split("```")[0]

        try:
            data = json.loads(json_text.strip())
            subtasks: list[Subtask] = []
            for st in data.get("subtasks", []):
                agent_name = st.get("assign_to", "")
                if agent_name not in self._crew.agents:
                    agent_name = (
                        specialist_names[0]
                        if specialist_names
                        else self._crew.orchestrator
                    )
                subtasks.append(
                    Subtask(
                        id=st.get("id", str(len(subtasks) + 1)),
                        description=st.get("description", ""),
                        assigned_to=agent_name,
                    )
                )
            if subtasks:
                return subtasks
        except (json.JSONDecodeError, KeyError, IndexError):
            pass

        # Fallback: single subtask for the first specialist.
        fallback_agent = specialist_names[0] if specialist_names else self._crew.orchestrator
        return [Subtask(id="1", description=user_task, assigned_to=fallback_agent)]

    # -- Phase 2: Execution -------------------------------------------------

    async def _execute_subtask(self, subtask: Subtask, run: CrewRun) -> None:
        """Execute a single subtask with its assigned agent (retry once)."""
        agent = self._crew.agents.get(subtask.assigned_to)
        if not agent:
            subtask.status = "failed"
            subtask.result = f"Agent '{subtask.assigned_to}' not found"
            return

        subtask.status = "running"
        await self._on_event(
            {
                "type": "agent_start",
                "agent": subtask.assigned_to,
                "subtaskId": subtask.id,
                "model": agent.model,
            }
        )

        # Budget guard
        if self._total_cost >= self._crew.budget_limit_usd:
            subtask.status = "failed"
            subtask.result = "Budget limit exceeded"
            await self._on_event(
                {
                    "type": "agent_done",
                    "agent": subtask.assigned_to,
                    "subtaskId": subtask.id,
                }
            )
            return

        messages = [
            {"role": "system", "content": agent.system_prompt},
            {"role": "user", "content": subtask.description},
        ]

        last_exc: Exception | None = None
        for _attempt in range(2):  # first try + one retry
            try:
                text, in_tok, out_tok = await self._call_model_streaming(
                    agent.model,
                    messages,
                    agent.max_tokens,
                    agent_name=subtask.assigned_to,
                    subtask_id=subtask.id,
                )
                subtask.result = text
                subtask.input_tokens = in_tok
                subtask.output_tokens = out_tok
                subtask.cost_usd = self._estimate_cost(in_tok, out_tok, agent.model)
                self._total_cost += subtask.cost_usd
                subtask.status = "done"
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc

        if last_exc is not None:
            subtask.status = "failed"
            subtask.result = f"Failed after retry: {last_exc}"

        await self._on_event(
            {
                "type": "agent_done",
                "agent": subtask.assigned_to,
                "subtaskId": subtask.id,
            }
        )

    # -- Phase 3: Synthesis -------------------------------------------------

    async def _synthesize(self, orchestrator: AgentDef, run: CrewRun) -> str:
        """Merge all subtask results into a single coherent answer."""
        results_summary = "\n\n".join(
            f"## Agent: {s.assigned_to} (Task: {s.description})\n"
            f"Status: {s.status}\n"
            f"Result:\n{s.result}"
            for s in run.subtasks
        )

        messages = [
            {"role": "system", "content": orchestrator.system_prompt},
            {
                "role": "user",
                "content": (
                    f"Original task: {run.user_task}\n\n"
                    f"Here are the results from each agent:\n\n"
                    f"{results_summary}\n\n"
                    f"Synthesize these into a coherent, complete final response."
                ),
            },
        ]

        # Budget guard before synthesis
        if self._total_cost >= self._crew.budget_limit_usd:
            return (
                "Budget limit reached before synthesis. "
                "Raw agent results are available in the subtask list."
            )

        text, in_tok, out_tok = await self._call_model_streaming(
            orchestrator.model,
            messages,
            orchestrator.max_tokens,
            synthesis=True,
        )

        cost = self._estimate_cost(in_tok, out_tok, orchestrator.model)
        self._total_cost += cost

        return text

    # -- OpenRouter transport -----------------------------------------------

    def _request_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/code-swap",
            "X-Title": "code-swap",
        }

    async def _call_model(
        self,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> tuple[str, int, int]:
        """Non-streaming call to OpenRouter. Returns (text, in_tok, out_tok)."""
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=self._request_headers(),
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return text, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)

    async def _call_model_streaming(
        self,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        agent_name: str = "",
        subtask_id: str = "",
        synthesis: bool = False,
    ) -> tuple[str, int, int]:
        """Streaming call to OpenRouter, pushing delta events via *on_event*."""
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        chunks: list[str] = []
        input_tokens = 0
        output_tokens = 0

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=self._request_headers(),
                json=body,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[len("data:") :].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError:
                        continue

                    # Delta content
                    choices = event.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        text = delta.get("content")
                        if text:
                            chunks.append(text)
                            if synthesis:
                                await self._on_event(
                                    {"type": "synthesis_delta", "text": text}
                                )
                            elif agent_name:
                                await self._on_event(
                                    {
                                        "type": "agent_delta",
                                        "agent": agent_name,
                                        "subtaskId": subtask_id,
                                        "text": text,
                                    }
                                )

                    # Usage (typically on the final chunk)
                    usage = event.get("usage")
                    if usage:
                        input_tokens = usage.get("prompt_tokens", 0)
                        output_tokens = usage.get("completion_tokens", 0)

        full_text = "".join(chunks)
        # Fallback token estimate when the API omits usage data.
        if not output_tokens:
            output_tokens = max(1, len(full_text) // 4)

        return full_text, input_tokens, output_tokens

    # -- Cost estimation ----------------------------------------------------

    def _estimate_cost(
        self, input_tokens: int, output_tokens: int, model: str
    ) -> float:
        """Estimate USD cost for a request using the local pricing table."""
        pricing = get_model_pricing(model)
        if pricing:
            return (input_tokens * pricing.input / 1_000_000) + (
                output_tokens * pricing.output / 1_000_000
            )
        # Conservative fallback for unknown models.
        return (input_tokens * 1.0 / 1_000_000) + (output_tokens * 5.0 / 1_000_000)

    @property
    def total_cost(self) -> float:
        """Accumulated USD cost across all API calls in this engine run."""
        return self._total_cost
