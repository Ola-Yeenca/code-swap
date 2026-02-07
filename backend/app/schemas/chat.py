from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ChatMode, Provider


class ChatSessionCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = "New Chat"
    chat_mode: ChatMode = Field(default=ChatMode.SINGLE, alias="chatMode")
    workspace_id: str | None = Field(default=None, alias="workspaceId")


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    title: str
    chat_mode: ChatMode = Field(alias="chatMode")
    workspace_id: str | None = Field(default=None, alias="workspaceId")
    user_id: str = Field(alias="userId")


class ContentPart(BaseModel):
    type: str
    text: str | None = None
    image_url: str | None = Field(default=None, alias="imageUrl")
    file_id: str | None = Field(default=None, alias="fileId")

    model_config = ConfigDict(populate_by_name=True)


class ChatStreamRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(alias="sessionId")
    provider: Provider
    model_id: str = Field(alias="modelId")
    key_mode: str = Field(default="vault", alias="keyMode")
    local_api_key: str | None = Field(default=None, alias="localApiKey")
    parts: list[ContentPart]


class CompareTarget(BaseModel):
    provider: Provider
    model_id: str = Field(alias="modelId")
    key_mode: str = Field(default="vault", alias="keyMode")
    local_api_key: str | None = Field(default=None, alias="localApiKey")

    model_config = ConfigDict(populate_by_name=True)


class CompareStreamRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(alias="sessionId")
    left: CompareTarget
    right: CompareTarget
    parts: list[ContentPart]
