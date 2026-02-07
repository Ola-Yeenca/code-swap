from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.session import get_db
from app.models import UsageEvent
from app.schemas.usage import UsageEventResponse, UsageSummaryResponse
from app.services.usage_service import usage_summary, workspace_usage_summary
from app.services.workspace_access import require_workspace_member

router = APIRouter(prefix="")


@router.get("/usage/summary", response_model=UsageSummaryResponse)
def get_usage_summary(
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UsageSummaryResponse:
    if workspace_id:
        require_workspace_member(db, workspace_id, user.id)
        summary = workspace_usage_summary(db, workspace_id)
    else:
        summary = usage_summary(db, user.id)
    return UsageSummaryResponse(**summary)


@router.get("/usage/events", response_model=list[UsageEventResponse])
def get_usage_events(
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[UsageEventResponse]:
    if workspace_id:
        require_workspace_member(db, workspace_id, user.id)
        query = db.query(UsageEvent).filter(UsageEvent.workspace_id == workspace_id)
    else:
        query = db.query(UsageEvent).filter(UsageEvent.user_id == user.id)

    events = query.order_by(UsageEvent.created_at.desc()).limit(200).all()
    return [UsageEventResponse.model_validate(event) for event in events]
