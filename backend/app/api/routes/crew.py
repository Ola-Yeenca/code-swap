from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from app.schemas.crew import CrewRunRequest
from app.services.crew_service import stream_crew_chat

router = APIRouter(prefix="/crew")


@router.post("/stream")
async def crew_stream(request: Request, body: CrewRunRequest):
    """Stream a crew execution as Server-Sent Events."""
    api_key = request.headers.get("x-openrouter-key", "")

    return StreamingResponse(
        stream_crew_chat(body, api_key),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
