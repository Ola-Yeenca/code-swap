import uuid


def build_storage_key(user_id: str, filename: str) -> str:
    return f"uploads/{user_id}/{uuid.uuid4()}-{filename}"


def build_presigned_upload_url(storage_key: str) -> str:
    # Placeholder URL for local development.
    return f"https://uploads.example.local/{storage_key}"
