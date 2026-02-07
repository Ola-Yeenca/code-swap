from pydantic import BaseModel, ConfigDict, Field


class CheckoutSessionRequest(BaseModel):
    workspace_id: str = Field(alias="workspaceId")

    model_config = ConfigDict(populate_by_name=True)


class CheckoutSessionResponse(BaseModel):
    url: str
    session_id: str = Field(alias="sessionId")
    customer_id: str = Field(alias="customerId")

    model_config = ConfigDict(populate_by_name=True)


class BillingPortalRequest(BaseModel):
    workspace_id: str = Field(alias="workspaceId")

    model_config = ConfigDict(populate_by_name=True)


class BillingPortalResponse(BaseModel):
    url: str


class BillingStatusResponse(BaseModel):
    workspace_id: str = Field(alias="workspaceId")
    has_customer: bool = Field(alias="hasCustomer")
    customer_id: str | None = Field(default=None, alias="customerId")
    subscription_status: str = Field(alias="subscriptionStatus")
    current_period_end: str | None = Field(default=None, alias="currentPeriodEnd")

    model_config = ConfigDict(populate_by_name=True)


class EntitlementResponse(BaseModel):
    feature_key: str = Field(alias="featureKey")
    is_enabled: bool = Field(alias="isEnabled")
    quota: int | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class BillingWebhookResponse(BaseModel):
    ok: bool
    event_type: str = Field(alias="eventType")
    workspace_id: str | None = Field(default=None, alias="workspaceId")

    model_config = ConfigDict(populate_by_name=True)
