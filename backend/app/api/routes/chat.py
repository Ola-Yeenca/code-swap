from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.session import get_db
from app.models import ChatSession
from app.schemas.chat import ChatSessionCreateRequest, ChatSessionResponse, ChatStreamRequest
from app.services.chat_service import stream_single_chat
from app.services.workspace_access import require_chat_session_access, require_workspace_member

router = APIRouter(prefix="")


@router.post("/chat/sessions", response_model=ChatSessionResponse)
def create_chat_session(
    payload: ChatSessionCreateRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatSessionResponse:
    if payload.workspace_id:
        require_workspace_member(db, payload.workspace_id, user.id)

    session_row = ChatSession(
        title=payload.title,
        chat_mode=payload.chat_mode,
        workspace_id=payload.workspace_id,
        user_id=user.id,
    )
    db.add(session_row)
    db.commit()
    db.refresh(session_row)
    return ChatSessionResponse.model_validate(session_row)


@router.get("/chat/sessions", response_model=list[ChatSessionResponse])
def list_chat_sessions(
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ChatSessionResponse]:
    query = db.query(ChatSession).filter(ChatSession.deleted_at.is_(None))
    if workspace_id:
        require_workspace_member(db, workspace_id, user.id)
        rows = query.filter(ChatSession.workspace_id == workspace_id).order_by(ChatSession.created_at.desc()).all()
    else:
        rows = query.filter(ChatSession.user_id == user.id).order_by(ChatSession.created_at.desc()).all()
    return [ChatSessionResponse.model_validate(row) for row in rows]


@router.get("/chat/sessions/{session_id}", response_model=ChatSessionResponse)
def get_chat_session(
    session_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatSessionResponse:
    row = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.deleted_at.is_(None)).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    require_chat_session_access(db, user.id, row)
    return ChatSessionResponse.model_validate(row)


@router.post("/chat/messages/stream")
async def chat_stream(
    payload: ChatStreamRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    async def generator():
        async for event in stream_single_chat(db, user.id, payload):
            yield event

    return StreamingResponse(generator(), media_type="text/event-stream")
