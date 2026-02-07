from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import ChatSession, File, Role, Workspace, WorkspaceMember


def get_workspace(db: Session, workspace_id: str) -> Workspace:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return workspace


def get_workspace_membership(db: Session, workspace_id: str, user_id: str) -> WorkspaceMember | None:
    return (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id)
        .first()
    )


def require_workspace_member(db: Session, workspace_id: str, user_id: str) -> WorkspaceMember:
    membership = get_workspace_membership(db, workspace_id, user_id)
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace access denied")
    return membership


def require_workspace_role(
    db: Session,
    workspace_id: str,
    user_id: str,
    allowed_roles: set[Role],
) -> WorkspaceMember:
    membership = require_workspace_member(db, workspace_id, user_id)
    if membership.role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient workspace role")
    return membership


def can_access_chat_session(db: Session, user_id: str, chat_session: ChatSession) -> bool:
    if chat_session.user_id == user_id:
        return True
    if not chat_session.workspace_id:
        return False
    return get_workspace_membership(db, chat_session.workspace_id, user_id) is not None


def require_chat_session_access(db: Session, user_id: str, chat_session: ChatSession) -> None:
    if not can_access_chat_session(db, user_id, chat_session):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")


def require_chat_session_manage_permission(db: Session, user_id: str, chat_session: ChatSession) -> None:
    if chat_session.user_id == user_id:
        return
    if not chat_session.workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    membership = require_workspace_member(db, chat_session.workspace_id, user_id)
    if membership.role not in {Role.OWNER, Role.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")


def can_access_file(db: Session, user_id: str, file_row: File) -> bool:
    if file_row.user_id == user_id:
        return True
    if not file_row.workspace_id:
        return False
    return get_workspace_membership(db, file_row.workspace_id, user_id) is not None


def require_file_access(db: Session, user_id: str, file_row: File) -> None:
    if not can_access_file(db, user_id, file_row):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")


def require_file_manage_permission(db: Session, user_id: str, file_row: File) -> None:
    if file_row.user_id == user_id:
        return
    if not file_row.workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    membership = require_workspace_member(db, file_row.workspace_id, user_id)
    if membership.role not in {Role.OWNER, Role.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
