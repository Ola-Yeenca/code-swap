from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.security import KeyCipher, mask_api_key
from app.db.session import get_db
from app.models import KeyMode, ProviderKey
from app.schemas.keys import KeyCreateRequest, KeyResponse

router = APIRouter(prefix="")
cipher = KeyCipher()


@router.post("/keys", response_model=KeyResponse)
def create_key(
    payload: KeyCreateRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KeyResponse:
    encrypted_api_key = None
    if payload.key_mode == KeyMode.VAULT:
        encrypted_api_key = cipher.encrypt(payload.api_key)

    key = ProviderKey(
        user_id=user.id,
        provider=payload.provider,
        key_mode=payload.key_mode,
        label=payload.label,
        masked_hint=mask_api_key(payload.api_key),
        encrypted_api_key=encrypted_api_key,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return KeyResponse.model_validate(key)


@router.get("/keys", response_model=list[KeyResponse])
def list_keys(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[KeyResponse]:
    keys = (
        db.query(ProviderKey)
        .filter(ProviderKey.user_id == user.id)
        .order_by(ProviderKey.created_at.desc())
        .all()
    )
    return [KeyResponse.model_validate(k) for k in keys]


@router.delete("/keys/{key_id}")
def delete_key(
    key_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    key = db.query(ProviderKey).filter(ProviderKey.id == key_id, ProviderKey.user_id == user.id).first()
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
    db.delete(key)
    db.commit()
    return {"ok": True}
