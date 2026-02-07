from __future__ import annotations

import json
from datetime import UTC, datetime

import stripe
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import BillingCustomer, BillingSubscription, Entitlement, Role, Workspace, WorkspaceMember

settings = get_settings()

DEFAULT_ENTITLEMENTS = {
    "compare.mode": True,
    "file.analysis": True,
    "workspace.invites": True,
}


class BillingDisabledError(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="Billing is disabled")


def ensure_billing_enabled() -> None:
    if not settings.billing_enabled:
        raise BillingDisabledError()


def require_workspace_owner(db: Session, workspace_id: str, user_id: str) -> Workspace:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    membership = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.role == Role.OWNER,
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required")
    return workspace


def _ensure_stripe_key() -> bool:
    if not settings.stripe_secret_key:
        return False
    stripe.api_key = settings.stripe_secret_key
    return True


def _get_or_create_customer(
    db: Session,
    workspace: Workspace,
    owner_email: str,
) -> BillingCustomer:
    customer = db.query(BillingCustomer).filter(BillingCustomer.workspace_id == workspace.id).first()
    if customer:
        return customer

    if _ensure_stripe_key():
        stripe_customer = stripe.Customer.create(
            email=owner_email,
            metadata={"workspace_id": workspace.id},
        )
        stripe_customer_id = stripe_customer["id"]
    else:
        stripe_customer_id = f"cus_mock_{workspace.id.replace('-', '')[:16]}"

    customer = BillingCustomer(
        workspace_id=workspace.id,
        stripe_customer_id=stripe_customer_id,
        status="active",
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def create_checkout_session(
    db: Session,
    workspace_id: str,
    owner_id: str,
    owner_email: str,
) -> dict[str, str]:
    ensure_billing_enabled()
    workspace = require_workspace_owner(db, workspace_id, owner_id)
    customer = _get_or_create_customer(db, workspace, owner_email)

    if _ensure_stripe_key() and settings.stripe_price_id:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer.stripe_customer_id,
            line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
            success_url=settings.billing_success_url,
            cancel_url=settings.billing_cancel_url,
            metadata={"workspace_id": workspace.id},
            allow_promotion_codes=True,
        )
        session_id = session["id"]
        session_url = session["url"]
    else:
        session_id = f"cs_mock_{workspace.id.replace('-', '')[:16]}"
        session_url = f"https://checkout.stripe.com/pay/{session_id}"

    return {
        "url": session_url,
        "session_id": session_id,
        "customer_id": customer.stripe_customer_id,
    }


def create_portal_session(
    db: Session,
    workspace_id: str,
    owner_id: str,
) -> dict[str, str]:
    ensure_billing_enabled()
    workspace = require_workspace_owner(db, workspace_id, owner_id)
    customer = db.query(BillingCustomer).filter(BillingCustomer.workspace_id == workspace.id).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Billing customer not found")

    if _ensure_stripe_key():
        portal = stripe.billing_portal.Session.create(
            customer=customer.stripe_customer_id,
            return_url=settings.billing_portal_return_url,
        )
        return {"url": portal["url"]}

    return {"url": f"https://billing.stripe.com/p/session/mock_{workspace.id[:8]}"}


def upsert_entitlements(db: Session, workspace_id: str, is_active: bool) -> None:
    for feature_key, default_enabled in DEFAULT_ENTITLEMENTS.items():
        row = (
            db.query(Entitlement)
            .filter(Entitlement.workspace_id == workspace_id, Entitlement.feature_key == feature_key)
            .first()
        )
        enabled = bool(default_enabled and is_active)
        if row:
            row.is_enabled = enabled
        else:
            db.add(
                Entitlement(
                    workspace_id=workspace_id,
                    feature_key=feature_key,
                    is_enabled=enabled,
                )
            )


def _upsert_subscription(
    db: Session,
    workspace_id: str,
    stripe_subscription_id: str,
    status_value: str,
    period_end: datetime | None,
) -> BillingSubscription:
    row = (
        db.query(BillingSubscription)
        .filter(BillingSubscription.workspace_id == workspace_id)
        .first()
    )
    if not row:
        row = BillingSubscription(
            workspace_id=workspace_id,
            stripe_subscription_id=stripe_subscription_id,
            status=status_value,
            current_period_end=period_end,
        )
        db.add(row)
    else:
        row.stripe_subscription_id = stripe_subscription_id
        row.status = status_value
        row.current_period_end = period_end
    return row


def _subscription_payload_to_values(payload: dict) -> tuple[str, datetime | None, str]:
    sub_id = payload.get("id") or "sub_unknown"
    status_value = payload.get("status") or "unknown"
    period_end_value = payload.get("current_period_end")
    period_end = None
    if isinstance(period_end_value, (int, float)):
        period_end = datetime.fromtimestamp(period_end_value, tz=UTC)
    return sub_id, period_end, status_value


def process_billing_webhook(
    db: Session,
    body: bytes,
    stripe_signature: str | None,
) -> dict[str, str | bool]:
    ensure_billing_enabled()

    if _ensure_stripe_key() and settings.stripe_webhook_secret:
        if not stripe_signature:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Stripe signature")
        event = stripe.Webhook.construct_event(body, stripe_signature, settings.stripe_webhook_secret)
    else:
        try:
            event = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook body") from exc

    event_type = event.get("type", "unknown")
    obj = event.get("data", {}).get("object", {})
    metadata = obj.get("metadata") or {}
    workspace_id = metadata.get("workspace_id")

    if not workspace_id:
        customer_id = obj.get("customer")
        if customer_id:
            customer = (
                db.query(BillingCustomer)
                .filter(BillingCustomer.stripe_customer_id == customer_id)
                .first()
            )
            workspace_id = customer.workspace_id if customer else None

    if workspace_id and event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "checkout.session.completed",
    }:
        if event_type == "checkout.session.completed":
            subscription_id = obj.get("subscription") or "sub_pending"
            row = _upsert_subscription(
                db,
                workspace_id=workspace_id,
                stripe_subscription_id=subscription_id,
                status_value="active",
                period_end=None,
            )
            upsert_entitlements(db, workspace_id, is_active=True)
        else:
            subscription_id, period_end, status_value = _subscription_payload_to_values(obj)
            row = _upsert_subscription(
                db,
                workspace_id=workspace_id,
                stripe_subscription_id=subscription_id,
                status_value=status_value,
                period_end=period_end,
            )
            upsert_entitlements(db, workspace_id, is_active=status_value in {"active", "trialing"})

        _ = row
        db.commit()

    return {"ok": True, "event_type": event_type, "workspace_id": workspace_id or ""}


def get_billing_status(
    db: Session,
    workspace_id: str,
    user_id: str,
) -> dict:
    ensure_billing_enabled()
    require_workspace_owner(db, workspace_id, user_id)
    customer = db.query(BillingCustomer).filter(BillingCustomer.workspace_id == workspace_id).first()
    subscription = (
        db.query(BillingSubscription)
        .filter(BillingSubscription.workspace_id == workspace_id)
        .first()
    )

    return {
        "workspace_id": workspace_id,
        "has_customer": bool(customer),
        "customer_id": customer.stripe_customer_id if customer else None,
        "subscription_status": subscription.status if subscription else "none",
        "current_period_end": subscription.current_period_end.isoformat()
        if subscription and subscription.current_period_end
        else None,
    }


def list_entitlements(
    db: Session,
    workspace_id: str,
    user_id: str,
) -> list[Entitlement]:
    ensure_billing_enabled()
    require_workspace_owner(db, workspace_id, user_id)
    return (
        db.query(Entitlement)
        .filter(Entitlement.workspace_id == workspace_id)
        .order_by(Entitlement.feature_key.asc())
        .all()
    )


def assert_workspace_feature(
    db: Session,
    workspace_id: str | None,
    feature_key: str,
) -> None:
    if not workspace_id:
        return
    if not settings.billing_enabled:
        return

    entitlement = (
        db.query(Entitlement)
        .filter(Entitlement.workspace_id == workspace_id, Entitlement.feature_key == feature_key)
        .first()
    )
    if entitlement and not entitlement.is_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Feature blocked: {feature_key}")
