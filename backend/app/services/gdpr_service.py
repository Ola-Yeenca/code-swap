from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import ChatMessage, ChatSession, DeletionJob, File, ProviderKey, UsageEvent, User


def export_user_data(db: Session, user_id: str) -> dict:
    user = db.query(User).filter(User.id == user_id).first()
    sessions = db.query(ChatSession).filter(ChatSession.user_id == user_id).all()
    messages = (
        db.query(ChatMessage)
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .filter(ChatSession.user_id == user_id)
        .all()
    )
    files = db.query(File).filter(File.user_id == user_id).all()
    keys = db.query(ProviderKey).filter(ProviderKey.user_id == user_id).all()
    usage = db.query(UsageEvent).filter(UsageEvent.user_id == user_id).all()

    return {
        "user": {"id": user.id, "email": user.email, "name": user.name} if user else None,
        "sessions": [
            {
                "id": s.id,
                "title": s.title,
                "chat_mode": s.chat_mode,
                "created_at": s.created_at.isoformat(),
            }
            for s in sessions
        ],
        "messages": [
            {
                "id": m.id,
                "session_id": m.session_id,
                "role": m.role,
                "provider": m.provider,
                "model_id": m.model_id,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
        "files": [
            {
                "id": f.id,
                "filename": f.filename,
                "mime_type": f.mime_type,
                "size_bytes": f.size_bytes,
                "status": f.status,
                "created_at": f.created_at.isoformat(),
            }
            for f in files
        ],
        "keys": [
            {
                "id": k.id,
                "provider": k.provider,
                "key_mode": k.key_mode,
                "masked_hint": k.masked_hint,
                "created_at": k.created_at.isoformat(),
            }
            for k in keys
        ],
        "usage": [
            {
                "id": u.id,
                "provider": u.provider,
                "model_id": u.model_id,
                "tokens_in": u.tokens_in,
                "tokens_out": u.tokens_out,
                "cost_usd": u.cost_usd,
                "created_at": u.created_at.isoformat(),
            }
            for u in usage
        ],
    }


def create_account_deletion_job(db: Session, user_id: str) -> DeletionJob:
    job = DeletionJob(
        user_id=user_id,
        job_type="account_delete",
        status="pending",
        scheduled_for=datetime.now(UTC) + timedelta(minutes=1),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
