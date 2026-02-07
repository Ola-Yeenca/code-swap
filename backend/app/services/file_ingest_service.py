from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models import File, FileChunk
from app.services.workspace_access import get_workspace_membership


def _estimate_tokens(text: str) -> int:
    # Rough approximation to keep metering deterministic in early versions.
    return max(1, len(text.split()))


def _chunk_text(text: str, max_words: int = 220) -> list[str]:
    words = re.split(r"\s+", text.strip())
    if not words or words == [""]:
        return []

    chunks: list[str] = []
    for idx in range(0, len(words), max_words):
        chunk = " ".join(words[idx : idx + max_words])
        chunks.append(chunk)
    return chunks


def ingest_file(db: Session, file_id: str) -> int:
    file_row = db.query(File).filter(File.id == file_id).first()
    if not file_row:
        raise ValueError("File not found")

    raw_text = str(file_row.metadata_json.get("raw_text", "")).strip()
    if not raw_text:
        raw_text = (
            f"File {file_row.filename} has been uploaded. "
            "This placeholder ingest can be replaced with object storage extraction workers."
        )

    chunks = _chunk_text(raw_text)
    db.query(FileChunk).filter(FileChunk.file_id == file_row.id).delete()

    for i, chunk in enumerate(chunks):
        db.add(
            FileChunk(
                file_id=file_row.id,
                chunk_index=i,
                text_content=chunk,
                token_estimate=_estimate_tokens(chunk),
            )
        )

    file_row.status = "ingested"
    db.commit()
    return len(chunks)


def get_file_context(db: Session, file_ids: list[str]) -> str:
    if not file_ids:
        return ""
    chunks = (
        db.query(FileChunk)
        .filter(FileChunk.file_id.in_(file_ids))
        .order_by(FileChunk.file_id.asc(), FileChunk.chunk_index.asc())
        .limit(8)
        .all()
    )
    if not chunks:
        return ""
    return "\n\n".join(chunk.text_content for chunk in chunks)


def get_file_context_for_user(db: Session, user_id: str, file_ids: list[str]) -> str:
    if not file_ids:
        return ""

    files = db.query(File).filter(File.id.in_(file_ids), File.deleted_at.is_(None)).all()
    allowed_file_ids: list[str] = []
    for file_row in files:
        if file_row.user_id == user_id:
            allowed_file_ids.append(file_row.id)
            continue
        if file_row.workspace_id and get_workspace_membership(db, file_row.workspace_id, user_id):
            allowed_file_ids.append(file_row.id)

    if not allowed_file_ids:
        return ""

    chunks = (
        db.query(FileChunk)
        .filter(FileChunk.file_id.in_(allowed_file_ids))
        .order_by(FileChunk.file_id.asc(), FileChunk.chunk_index.asc())
        .limit(8)
        .all()
    )
    if not chunks:
        return ""
    return "\n\n".join(chunk.text_content for chunk in chunks)
