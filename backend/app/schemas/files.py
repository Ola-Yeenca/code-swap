from pydantic import BaseModel, ConfigDict, Field


class PresignUploadRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    filename: str
    mime_type: str = Field(alias="mimeType")
    size_bytes: int = Field(alias="sizeBytes")
    workspace_id: str | None = Field(default=None, alias="workspaceId")


class PresignUploadResponse(BaseModel):
    file_id: str = Field(alias="fileId")
    upload_url: str = Field(alias="uploadUrl")
    storage_key: str = Field(alias="storageKey")

    model_config = ConfigDict(populate_by_name=True)


class IngestResponse(BaseModel):
    file_id: str = Field(alias="fileId")
    chunks_created: int = Field(alias="chunksCreated")

    model_config = ConfigDict(populate_by_name=True)


class FileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    filename: str
    mime_type: str = Field(alias="mimeType")
    size_bytes: int = Field(alias="sizeBytes")
    status: str
    workspace_id: str | None = Field(default=None, alias="workspaceId")
