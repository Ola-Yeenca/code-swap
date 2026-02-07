from pydantic import BaseModel, EmailStr


class MagicLinkRequest(BaseModel):
    email: EmailStr


class MagicLinkRequestResponse(BaseModel):
    ok: bool
    token_preview: str | None = None


class MagicLinkVerifyRequest(BaseModel):
    token: str


class AuthStartResponse(BaseModel):
    url: str


class MeResponse(BaseModel):
    id: str
    email: str
    name: str | None = None
