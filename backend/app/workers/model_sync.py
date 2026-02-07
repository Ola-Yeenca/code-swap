from __future__ import annotations

from arq.connections import RedisSettings
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.model_catalog_service import refresh_model_catalog

settings = get_settings()


async def sync_models_job(ctx: dict) -> dict:
    user_id = ctx.get("user_id")
    if not user_id:
        return {"ok": False, "reason": "missing user_id"}
    db: Session = SessionLocal()
    try:
        status = await refresh_model_catalog(db, user_id=user_id)
        return {"ok": True, **status}
    finally:
        db.close()


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [sync_models_job]
    max_jobs = 20
