from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.session import get_db
from app.models import ChatSession
from app.services.gdpr_service import create_account_deletion_job, export_user_data
from app.services.workspace_access import require_chat_session_manage_permission

router = APIRouter(prefix="")


@router.get("/gdpr/export")
def gdpr_export(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return export_user_data(db, user.id)


@router.post("/gdpr/delete-account")
def gdpr_delete_account(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    job = create_account_deletion_job(db, user.id)
    return {"ok": True, "jobId": job.id}


@router.delete("/chat/sessions/{session_id}")
def delete_chat_session(
    session_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == user.id, ChatSession.deleted_at.is_(None))
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    require_chat_session_manage_permission(db, user.id, row)
    row.deleted_at = datetime.now(UTC)
    db.commit()
    return {"ok": True}
