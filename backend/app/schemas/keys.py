from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import KeyMode, Provider


class KeyCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: Provider
    key_mode: KeyMode = Field(alias="keyMode")
    api_key: str = Field(alias="apiKey", min_length=8)
    label: str | None = None


class KeyResponse(BaseModel):
    id: str
    provider: Provider
    key_mode: KeyMode = Field(alias="keyMode")
    label: str | None = None
    masked_hint: str = Field(alias="maskedHint")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
