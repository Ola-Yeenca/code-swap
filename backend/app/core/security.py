import base64
import hashlib
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.core.config import get_settings

settings = get_settings()


def _derive_fernet_key() -> bytes:
    if settings.encryption_key:
        raw = settings.encryption_key.encode("utf-8")
        try:
            # If already urlsafe base64 32-byte key this should work directly.
            Fernet(raw)
            return raw
        except Exception:
            pass

    digest = hashlib.sha256(settings.session_secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


class KeyCipher:
    def __init__(self) -> None:
        self._fernet = Fernet(_derive_fernet_key())

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")


def mask_api_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}...{api_key[-4:]}"


class SessionSigner:
    def __init__(self) -> None:
        self._serializer = URLSafeTimedSerializer(secret_key=settings.session_secret)

    def sign(self, user_id: str) -> str:
        return self._serializer.dumps({"user_id": user_id})

    def unsign(self, token: str, max_age_seconds: int = 60 * 60 * 24 * 30) -> str | None:
        try:
            payload = self._serializer.loads(token, max_age=max_age_seconds)
        except BadSignature:
            return None
        return payload.get("user_id")


class MagicLinkSigner:
    def __init__(self) -> None:
        self._serializer = URLSafeTimedSerializer(
            secret_key=settings.session_secret, salt=settings.magic_link_signer_salt
        )

    def sign_email(self, email: str) -> str:
        return self._serializer.dumps({"email": email, "exp": self._default_exp()})

    def verify(self, token: str, max_age_seconds: int = 60 * 15) -> str | None:
        try:
            payload = self._serializer.loads(token, max_age=max_age_seconds)
        except BadSignature:
            return None
        return payload.get("email")

    @staticmethod
    def _default_exp() -> str:
        return (datetime.now(UTC) + timedelta(minutes=15)).isoformat()
