from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import Provider


class ModelCatalogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: Provider
    model_id: str
    capabilities: dict
    is_active: bool
    deprecation_at: datetime | None = None
    last_synced_at: datetime


class ModelsListResponse(BaseModel):
    items: list[ModelCatalogResponse]
    stale: bool = False
    stale_reason: str | None = None
