import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.session import get_db
from app.models import Role, User, Workspace, WorkspaceInvite, WorkspaceMember
from app.schemas.workspaces import (
    InviteCreateRequest,
    InviteResponse,
    UpdateWorkspaceMemberRequest,
    WorkspaceCreateRequest,
    WorkspaceListResponse,
    WorkspaceMemberResponse,
    WorkspaceResponse,
    WorkspaceUsageResponse,
)
from app.services.notification_service import send_workspace_invite_email
from app.services.billing_service import upsert_entitlements
from app.services.usage_service import workspace_usage_summary
from app.services.workspace_access import (
    require_workspace_member,
    require_workspace_role,
)

router = APIRouter(prefix="")


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@router.post("/workspaces", response_model=WorkspaceResponse)
def create_workspace(
    payload: WorkspaceCreateRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceResponse:
    workspace = Workspace(name=payload.name, owner_id=user.id, data_region=payload.data_region)
    db.add(workspace)
    db.flush()

    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=Role.OWNER))
    upsert_entitlements(db, workspace.id, is_active=True)
    db.commit()
    db.refresh(workspace)
    return WorkspaceResponse.model_validate(workspace)


@router.get("/workspaces", response_model=list[WorkspaceListResponse])
def list_workspaces(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WorkspaceListResponse]:
    memberships = (
        db.query(WorkspaceMember, Workspace)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .filter(WorkspaceMember.user_id == user.id)
        .all()
    )
    return [
        WorkspaceListResponse(
            workspace=WorkspaceResponse.model_validate(workspace),
            role=membership.role,
        )
        for membership, workspace in memberships
    ]


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(
    workspace_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceResponse:
    require_workspace_member(db, workspace_id, user.id)
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return WorkspaceResponse.model_validate(workspace)


@router.get("/workspaces/{workspace_id}/members", response_model=list[WorkspaceMemberResponse])
def list_workspace_members(
    workspace_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WorkspaceMemberResponse]:
    require_workspace_member(db, workspace_id, user.id)
    rows = (
        db.query(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .filter(WorkspaceMember.workspace_id == workspace_id)
        .order_by(WorkspaceMember.created_at.asc())
        .all()
    )
    return [
        WorkspaceMemberResponse(
            userId=member.user_id,
            email=u.email,
            name=u.name,
            role=member.role,
        )
        for member, u in rows
    ]


@router.patch("/workspaces/{workspace_id}/members/{member_user_id}", response_model=WorkspaceMemberResponse)
def update_workspace_member(
    workspace_id: str,
    member_user_id: str,
    payload: UpdateWorkspaceMemberRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceMemberResponse:
    require_workspace_role(db, workspace_id, user.id, {Role.OWNER, Role.ADMIN})

    target_member = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == member_user_id)
        .first()
    )
    if not target_member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if target_member.role == Role.OWNER and payload.role != Role.OWNER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot demote workspace owner")
    if payload.role == Role.OWNER and target_member.role != Role.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Owner transfer flow is not implemented",
        )

    target_member.role = payload.role
    db.commit()

    target_user = db.query(User).filter(User.id == member_user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return WorkspaceMemberResponse(
        userId=target_member.user_id,
        email=target_user.email,
        name=target_user.name,
        role=target_member.role,
    )


@router.delete("/workspaces/{workspace_id}/members/{member_user_id}")
def remove_workspace_member(
    workspace_id: str,
    member_user_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    acting_member = require_workspace_member(db, workspace_id, user.id)

    target_member = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == member_user_id)
        .first()
    )
    if not target_member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    if target_member.role == Role.OWNER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove workspace owner")

    if member_user_id != user.id and acting_member.role not in {Role.OWNER, Role.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    db.delete(target_member)
    db.commit()
    return {"ok": True}


@router.post("/workspaces/{workspace_id}/invites", response_model=InviteResponse)
def invite_member(
    workspace_id: str,
    payload: InviteCreateRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InviteResponse:
    require_workspace_role(db, workspace_id, user.id, {Role.OWNER, Role.ADMIN})

    existing_member = (
        db.query(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .filter(WorkspaceMember.workspace_id == workspace_id, User.email == str(payload.email))
        .first()
    )
    if existing_member:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already in workspace")

    invite = (
        db.query(WorkspaceInvite)
        .filter(
            WorkspaceInvite.workspace_id == workspace_id,
            WorkspaceInvite.email == str(payload.email),
            WorkspaceInvite.accepted_at.is_(None),
        )
        .first()
    )

    if invite:
        invite.token = secrets.token_urlsafe(24)
        invite.role = payload.role
        invite.expires_at = datetime.now(UTC) + timedelta(days=7)
    else:
        invite = WorkspaceInvite(
            workspace_id=workspace_id,
            invited_by_user_id=user.id,
            email=str(payload.email),
            role=payload.role,
            token=secrets.token_urlsafe(24),
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        db.add(invite)

    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    delivery = send_workspace_invite_email(
        recipient_email=str(payload.email),
        workspace_name=workspace.name if workspace else workspace_id,
        inviter_email=user.email,
        invite_token=invite.token,
    )

    db.commit()
    db.refresh(invite)
    return InviteResponse(
        id=invite.id,
        email=invite.email,
        role=invite.role,
        token=invite.token,
        workspaceId=invite.workspace_id,
        expiresAt=invite.expires_at,
        acceptedAt=invite.accepted_at,
        deliveryStatus=delivery.status,
        inviteUrl=delivery.get("invite_url"),
    )


@router.get("/workspaces/{workspace_id}/invites", response_model=list[InviteResponse])
def list_invites(
    workspace_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[InviteResponse]:
    require_workspace_role(db, workspace_id, user.id, {Role.OWNER, Role.ADMIN})
    invites = (
        db.query(WorkspaceInvite)
        .filter(WorkspaceInvite.workspace_id == workspace_id)
        .order_by(WorkspaceInvite.created_at.desc())
        .all()
    )
    return [
        InviteResponse(
            id=invite.id,
            email=invite.email,
            role=invite.role,
            token=invite.token,
            workspaceId=invite.workspace_id,
            expiresAt=invite.expires_at,
            acceptedAt=invite.accepted_at,
        )
        for invite in invites
    ]


@router.post("/workspaces/{workspace_id}/invites/{invite_id}/resend", response_model=InviteResponse)
def resend_invite(
    workspace_id: str,
    invite_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InviteResponse:
    require_workspace_role(db, workspace_id, user.id, {Role.OWNER, Role.ADMIN})

    invite = (
        db.query(WorkspaceInvite)
        .filter(WorkspaceInvite.workspace_id == workspace_id, WorkspaceInvite.id == invite_id)
        .first()
    )
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if invite.accepted_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite already accepted")

    invite.token = secrets.token_urlsafe(24)
    invite.expires_at = datetime.now(UTC) + timedelta(days=7)

    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    delivery = send_workspace_invite_email(
        recipient_email=invite.email,
        workspace_name=workspace.name if workspace else workspace_id,
        inviter_email=user.email,
        invite_token=invite.token,
    )

    db.commit()
    db.refresh(invite)

    return InviteResponse(
        id=invite.id,
        email=invite.email,
        role=invite.role,
        token=invite.token,
        workspaceId=invite.workspace_id,
        expiresAt=invite.expires_at,
        acceptedAt=invite.accepted_at,
        deliveryStatus=delivery.status,
        inviteUrl=delivery.get("invite_url"),
    )


@router.delete("/workspaces/{workspace_id}/invites/{invite_id}")
def revoke_invite(
    workspace_id: str,
    invite_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    require_workspace_role(db, workspace_id, user.id, {Role.OWNER, Role.ADMIN})

    invite = (
        db.query(WorkspaceInvite)
        .filter(WorkspaceInvite.workspace_id == workspace_id, WorkspaceInvite.id == invite_id)
        .first()
    )
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")

    db.delete(invite)
    db.commit()
    return {"ok": True}


@router.post("/invites/{token}/accept")
def accept_invite(
    token: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    invite = (
        db.query(WorkspaceInvite)
        .filter(WorkspaceInvite.token == token, WorkspaceInvite.accepted_at.is_(None))
        .first()
    )
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
    if _as_aware_utc(invite.expires_at) < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite expired")
    if invite.email.lower() != user.email.lower():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invite email mismatch")

    exists = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == invite.workspace_id, WorkspaceMember.user_id == user.id)
        .first()
    )
    if not exists:
        db.add(WorkspaceMember(workspace_id=invite.workspace_id, user_id=user.id, role=invite.role))
    invite.accepted_at = datetime.now(UTC)
    db.commit()
    return {"ok": True}


@router.get("/workspaces/{workspace_id}/usage", response_model=WorkspaceUsageResponse)
def workspace_usage(
    workspace_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceUsageResponse:
    require_workspace_member(db, workspace_id, user.id)
    summary = workspace_usage_summary(db, workspace_id)
    return WorkspaceUsageResponse(**summary)
