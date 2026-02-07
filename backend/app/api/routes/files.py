from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.session import get_db
from app.models import File
from app.schemas.files import FileResponse, IngestResponse, PresignUploadRequest, PresignUploadResponse
from app.services.billing_service import assert_workspace_feature
from app.services.file_ingest_service import ingest_file
from app.services.storage_service import build_presigned_upload_url, build_storage_key
from app.services.workspace_access import (
    require_file_access,
    require_file_manage_permission,
    require_workspace_member,
)

router = APIRouter(prefix="")


@router.post("/files/presign-upload", response_model=PresignUploadResponse)
def presign_upload(
    payload: PresignUploadRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PresignUploadResponse:
    if payload.workspace_id:
        require_workspace_member(db, payload.workspace_id, user.id)
        assert_workspace_feature(db, payload.workspace_id, "file.analysis")

    storage_key = build_storage_key(user.id, payload.filename)
    file_row = File(
        workspace_id=payload.workspace_id,
        user_id=user.id,
        filename=payload.filename,
        mime_type=payload.mime_type,
        size_bytes=payload.size_bytes,
        storage_key=storage_key,
        status="uploaded",
    )
    db.add(file_row)
    db.commit()
    db.refresh(file_row)

    return PresignUploadResponse(
        fileId=file_row.id,
        uploadUrl=build_presigned_upload_url(storage_key),
        storageKey=storage_key,
    )


@router.get("/files", response_model=list[FileResponse])
def list_files(
    workspace_id: str | None = Query(default=None, alias="workspaceId"),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[FileResponse]:
    query = db.query(File).filter(File.deleted_at.is_(None))
    if workspace_id:
        require_workspace_member(db, workspace_id, user.id)
        rows = query.filter(File.workspace_id == workspace_id).order_by(File.created_at.desc()).all()
    else:
        rows = query.filter(File.user_id == user.id).order_by(File.created_at.desc()).all()

    return [FileResponse.model_validate(row) for row in rows]


@router.post("/files/{file_id}/ingest", response_model=IngestResponse)
def ingest(
    file_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IngestResponse:
    file_row = db.query(File).filter(File.id == file_id, File.deleted_at.is_(None)).first()
    if not file_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    require_file_access(db, user.id, file_row)
    assert_workspace_feature(db, file_row.workspace_id, "file.analysis")
    chunks = ingest_file(db, file_id)
    return IngestResponse(fileId=file_id, chunksCreated=chunks)


@router.get("/files/{file_id}", response_model=FileResponse)
def get_file(
    file_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    file_row = db.query(File).filter(File.id == file_id, File.deleted_at.is_(None)).first()
    if not file_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    require_file_access(db, user.id, file_row)
    return FileResponse.model_validate(file_row)


@router.delete("/files/{file_id}")
def delete_file(
    file_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    file_row = db.query(File).filter(File.id == file_id, File.deleted_at.is_(None)).first()
    if not file_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    require_file_manage_permission(db, user.id, file_row)
    file_row.deleted_at = datetime.now(UTC)
    file_row.status = "deleted"
    db.commit()
    return {"ok": True}
