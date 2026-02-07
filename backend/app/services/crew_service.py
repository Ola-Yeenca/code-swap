from __future__ import annotations
import asyncio
import json
from typing import AsyncGenerator
from app.schemas.crew import CrewRunRequest


async def stream_crew_chat(
    request: CrewRunRequest,
    api_key: str,
) -> AsyncGenerator[str, None]:
    """Stream crew execution as SSE events.

    Event types:
    - crew_start: {"type": "crew_start", "sessionId": "...", "agents": [...]}
    - plan: {"type": "plan", "subtasks": [...]}
    - agent_start: {"type": "agent_start", "agent": "...", "subtaskId": "...", "model": "..."}
    - agent_delta: {"type": "agent_delta", "agent": "...", "subtaskId": "...", "text": "..."}
    - agent_done: {"type": "agent_done", "agent": "...", "subtaskId": "..."}
    - synthesis_delta: {"type": "synthesis_delta", "text": "..."}
    - crew_done: {"type": "crew_done", "totalCost": 0.0327}
    - error: {"type": "error", "message": "..."}
    """
    from app.cli.engine import CrewEngine
    from app.cli.crew import load_crew, ensure_default_crews

    ensure_default_crews()

    queue: asyncio.Queue = asyncio.Queue()

    async def on_event(event: dict):
        await queue.put(event)

    try:
        crew_config = load_crew(request.crew_name)
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        return

    engine = CrewEngine(
        api_key=api_key,
        crew=crew_config,
        on_event=on_event,
    )

    task = asyncio.create_task(engine.execute(request.task))

    try:
        while not task.done() or not queue.empty():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.5)
                yield f"data: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                continue

        # Drain remaining events
        while not queue.empty():
            event = await queue.get()
            yield f"data: {json.dumps(event)}\n\n"

        # Get result for final summary
        result = await task
        yield f"data: {json.dumps({'type': 'crew_done', 'totalCost': sum(s.cost_usd for s in result.subtasks)})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        if not task.done():
            task.cancel()
