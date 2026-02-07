from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Provider


class UsageEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    provider: Provider
    model_id: str = Field(alias="modelId")
    event_type: str = Field(alias="eventType")
    tokens_in: int = Field(alias="tokensIn")
    tokens_out: int = Field(alias="tokensOut")
    cost_usd: float = Field(alias="costUsd")
    created_at: datetime = Field(alias="createdAt")


class UsageSummaryResponse(BaseModel):
    total_requests: int = Field(alias="totalRequests")
    total_tokens_in: int = Field(alias="totalTokensIn")
    total_tokens_out: int = Field(alias="totalTokensOut")
    total_cost_usd: float = Field(alias="totalCostUsd")

    model_config = ConfigDict(populate_by_name=True)
