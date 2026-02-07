from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.session import get_db
from app.schemas.billing import (
    BillingPortalRequest,
    BillingPortalResponse,
    BillingStatusResponse,
    BillingWebhookResponse,
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    EntitlementResponse,
)
from app.services.billing_service import (
    create_checkout_session,
    create_portal_session,
    get_billing_status,
    list_entitlements,
    process_billing_webhook,
)

router = APIRouter(prefix="")


@router.post("/billing/checkout-session", response_model=CheckoutSessionResponse)
def billing_checkout_session(
    payload: CheckoutSessionRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CheckoutSessionResponse:
    result = create_checkout_session(
        db=db,
        workspace_id=payload.workspace_id,
        owner_id=user.id,
        owner_email=user.email,
    )
    return CheckoutSessionResponse(
        url=result["url"],
        sessionId=result["session_id"],
        customerId=result["customer_id"],
    )


@router.post("/billing/portal-session", response_model=BillingPortalResponse)
def billing_portal_session(
    payload: BillingPortalRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BillingPortalResponse:
    result = create_portal_session(
        db=db,
        workspace_id=payload.workspace_id,
        owner_id=user.id,
    )
    return BillingPortalResponse(url=result["url"])


@router.get("/billing/status", response_model=BillingStatusResponse)
def billing_status(
    workspace_id: str = Query(alias="workspaceId"),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BillingStatusResponse:
    result = get_billing_status(db, workspace_id=workspace_id, user_id=user.id)
    return BillingStatusResponse(
        workspaceId=result["workspace_id"],
        hasCustomer=result["has_customer"],
        customerId=result["customer_id"],
        subscriptionStatus=result["subscription_status"],
        currentPeriodEnd=result["current_period_end"],
    )


@router.get("/billing/entitlements", response_model=list[EntitlementResponse])
def billing_entitlements(
    workspace_id: str = Query(alias="workspaceId"),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[EntitlementResponse]:
    rows = list_entitlements(db, workspace_id=workspace_id, user_id=user.id)
    return [EntitlementResponse.model_validate(row) for row in rows]


@router.post("/billing/webhook", response_model=BillingWebhookResponse)
async def billing_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
) -> BillingWebhookResponse:
    body = await request.body()
    result = process_billing_webhook(db, body=body, stripe_signature=stripe_signature)
    return BillingWebhookResponse(
        ok=bool(result.get("ok")),
        eventType=str(result.get("event_type", "unknown")),
        workspaceId=result.get("workspace_id") or None,
    )
