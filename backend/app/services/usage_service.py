from __future__ import annotations

from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import UsageDailyAgg, UsageEvent
from app.models.enums import Provider


def record_usage_event(
    db: Session,
    user_id: str,
    workspace_id: str | None,
    provider: Provider,
    model_id: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    event_type: str = "chat.completion",
) -> UsageEvent:
    event = UsageEvent(
        user_id=user_id,
        workspace_id=workspace_id,
        provider=provider,
        model_id=model_id,
        event_type=event_type,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
    )
    db.add(event)

    today = date.today()
    agg = (
        db.query(UsageDailyAgg)
        .filter(
            UsageDailyAgg.date == today,
            UsageDailyAgg.user_id == user_id,
            UsageDailyAgg.workspace_id == workspace_id,
            UsageDailyAgg.provider == provider,
            UsageDailyAgg.model_id == model_id,
        )
        .first()
    )
    if not agg:
        agg = UsageDailyAgg(
            date=today,
            user_id=user_id,
            workspace_id=workspace_id,
            provider=provider,
            model_id=model_id,
            total_requests=1,
            total_tokens_in=tokens_in,
            total_tokens_out=tokens_out,
            total_cost_usd=cost_usd,
        )
        db.add(agg)
    else:
        agg.total_requests += 1
        agg.total_tokens_in += tokens_in
        agg.total_tokens_out += tokens_out
        agg.total_cost_usd += cost_usd

    db.commit()
    db.refresh(event)
    return event


def usage_summary(db: Session, user_id: str) -> dict[str, float | int]:
    row = (
        db.query(
            func.count(UsageEvent.id),
            func.coalesce(func.sum(UsageEvent.tokens_in), 0),
            func.coalesce(func.sum(UsageEvent.tokens_out), 0),
            func.coalesce(func.sum(UsageEvent.cost_usd), 0.0),
        )
        .filter(UsageEvent.user_id == user_id)
        .first()
    )

    total_requests, total_tokens_in, total_tokens_out, total_cost_usd = row or (0, 0, 0, 0.0)
    return {
        "totalRequests": int(total_requests or 0),
        "totalTokensIn": int(total_tokens_in or 0),
        "totalTokensOut": int(total_tokens_out or 0),
        "totalCostUsd": float(total_cost_usd or 0.0),
    }


def workspace_usage_summary(db: Session, workspace_id: str) -> dict[str, float | int]:
    row = (
        db.query(
            func.count(UsageEvent.id),
            func.coalesce(func.sum(UsageEvent.tokens_in), 0),
            func.coalesce(func.sum(UsageEvent.tokens_out), 0),
            func.coalesce(func.sum(UsageEvent.cost_usd), 0.0),
        )
        .filter(UsageEvent.workspace_id == workspace_id)
        .first()
    )

    total_requests, total_tokens_in, total_tokens_out, total_cost_usd = row or (0, 0, 0, 0.0)
    return {
        "totalRequests": int(total_requests or 0),
        "totalTokensIn": int(total_tokens_in or 0),
        "totalTokensOut": int(total_tokens_out or 0),
        "totalCostUsd": float(total_cost_usd or 0.0),
    }
