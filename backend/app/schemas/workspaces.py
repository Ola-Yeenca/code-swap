from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import DataRegion, Role


class WorkspaceCreateRequest(BaseModel):
    name: str
    data_region: DataRegion = Field(default=DataRegion.US, alias="dataRegion")

    model_config = ConfigDict(populate_by_name=True)


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    name: str
    owner_id: str = Field(alias="ownerId")
    data_region: DataRegion = Field(alias="dataRegion")


class WorkspaceListResponse(BaseModel):
    workspace: WorkspaceResponse
    role: Role


class WorkspaceMemberResponse(BaseModel):
    user_id: str = Field(alias="userId")
    email: EmailStr
    name: str | None = None
    role: Role

    model_config = ConfigDict(populate_by_name=True)


class UpdateWorkspaceMemberRequest(BaseModel):
    role: Role


class InviteCreateRequest(BaseModel):
    email: EmailStr
    role: Role = Role.MEMBER


class InviteResponse(BaseModel):
    id: str
    email: EmailStr
    role: Role
    token: str
    workspace_id: str = Field(alias="workspaceId")
    expires_at: datetime = Field(alias="expiresAt")
    accepted_at: datetime | None = Field(default=None, alias="acceptedAt")
    delivery_status: str | None = Field(default=None, alias="deliveryStatus")
    invite_url: str | None = Field(default=None, alias="inviteUrl")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class WorkspaceUsageResponse(BaseModel):
    total_requests: int = Field(alias="totalRequests")
    total_tokens_in: int = Field(alias="totalTokensIn")
    total_tokens_out: int = Field(alias="totalTokensOut")
    total_cost_usd: float = Field(alias="totalCostUsd")

    model_config = ConfigDict(populate_by_name=True)
