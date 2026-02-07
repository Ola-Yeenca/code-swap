from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.auth import create_session, get_current_user
from app.core.config import get_settings
from app.core.security import MagicLinkSigner
from app.db.session import get_db
from app.models import User
from app.schemas.auth import (
    AuthStartResponse,
    MagicLinkRequest,
    MagicLinkRequestResponse,
    MagicLinkVerifyRequest,
    MeResponse,
)

router = APIRouter(prefix="")
magic_signer = MagicLinkSigner()
settings = get_settings()


@router.post("/auth/magic-link/request", response_model=MagicLinkRequestResponse)
def request_magic_link(payload: MagicLinkRequest) -> MagicLinkRequestResponse:
    token = magic_signer.sign_email(str(payload.email))
    # In production, send this token by email provider. Returned only for initial integration.
    return MagicLinkRequestResponse(ok=True, token_preview=token)


@router.post("/auth/magic-link/verify")
def verify_magic_link(
    payload: MagicLinkVerifyRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    email = magic_signer.verify(payload.token)
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid magic link")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, name=email.split("@")[0])
        db.add(user)
        db.commit()
        db.refresh(user)

    session_token = create_session(db, user.id)
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return {"ok": True}


@router.get("/auth/google/start", response_model=AuthStartResponse)
def google_start() -> AuthStartResponse:
    if not settings.google_client_id:
        return AuthStartResponse(url="/v1/auth/google/callback?email=demo@example.com")
    # Placeholder start URL for OAuth dance; production app should include state + nonce.
    return AuthStartResponse(url="https://accounts.google.com/o/oauth2/v2/auth")


@router.get("/auth/google/callback")
def google_callback(
    response: Response,
    email: str = Query(default="demo@example.com"),
    db: Session = Depends(get_db),
) -> dict:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, name=email.split("@")[0])
        db.add(user)
        db.commit()
        db.refresh(user)

    session_token = create_session(db, user.id)
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return {"ok": True}


@router.post("/auth/logout")
def logout(response: Response) -> dict:
    response.delete_cookie("session_token")
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
def me(user=Depends(get_current_user)) -> MeResponse:
    return MeResponse(id=user.id, email=user.email, name=user.name)
