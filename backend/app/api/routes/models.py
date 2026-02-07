from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.enums import Provider
from app.schemas.models import ModelsListResponse
from app.services.model_catalog_service import (
    list_models,
    refresh_model_catalog,
    should_refresh_model_catalog,
)

router = APIRouter(prefix="")
settings = get_settings()


@router.get("/models", response_model=ModelsListResponse)
async def get_models(
    provider: Provider | None = Query(default=None),
    capability: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> ModelsListResponse:
    stale = False
    stale_reason = None

    if should_refresh_model_catalog(
        db=db,
        user_id=user.id,
        provider=provider,
        max_age_minutes=settings.model_catalog_refresh_minutes,
    ):
        status = await refresh_model_catalog(db, user_id=user.id, provider=provider)
        stale = bool(status.get("stale"))
        reason = status.get("stale_reason")
        stale_reason = reason if isinstance(reason, str) and reason else None

    rows = list_models(db, provider=provider, capability=capability)
    return ModelsListResponse(items=rows, stale=stale, stale_reason=stale_reason)


@router.post("/models/refresh")
async def refresh_models(
    provider: Provider | None = Query(default=None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
) -> dict:
    status = await refresh_model_catalog(db, user_id=user.id, provider=provider)
    return {"ok": True, **status}
