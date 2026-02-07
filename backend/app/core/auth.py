from datetime import UTC, datetime, timedelta

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import SessionSigner
from app.db.session import get_db
from app.models import Session as UserSession
from app.models import User


class CurrentUser:
    def __init__(self, user: User) -> None:
        self.id = user.id
        self.email = user.email
        self.name = user.name


session_signer = SessionSigner()


def create_session(db: Session, user_id: str) -> str:
    token = session_signer.sign(user_id)
    db.add(
        UserSession(user_id=user_id, expires_at=datetime.now(UTC) + timedelta(days=30))
    )
    db.commit()
    return token


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    x_dev_user_email: str | None = Header(default=None),
) -> CurrentUser:
    token = request.cookies.get("session_token")
    if token:
        user_id = session_signer.unsign(token)
        if user_id:
            user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
            if user:
                return CurrentUser(user)

    if x_dev_user_email:
        user = db.query(User).filter(User.email == x_dev_user_email).first()
        if not user:
            user = User(email=x_dev_user_email, name=x_dev_user_email.split("@")[0])
            db.add(user)
            db.commit()
            db.refresh(user)
        return CurrentUser(user)

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
