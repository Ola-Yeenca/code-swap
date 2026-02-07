from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.session import get_db
from app.schemas.chat import CompareStreamRequest
from app.services.chat_service import stream_compare_chat

router = APIRouter(prefix="")


@router.post("/compare/messages/stream")
async def compare_stream(
    payload: CompareStreamRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    async def generator():
        async for event in stream_compare_chat(db, user.id, payload):
            yield event

    return StreamingResponse(generator(), media_type="text/event-stream")
