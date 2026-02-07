from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import ChatMessage, ChatSession
from app.models.enums import Provider
from app.schemas.chat import ChatStreamRequest, CompareStreamRequest
from app.services.billing_service import assert_workspace_feature
from app.services.file_ingest_service import get_file_context_for_user
from app.services.provider_service import provider_registry
from app.services.providers_base import ProviderMessagePart
from app.services.usage_service import record_usage_event
from app.services.workspace_access import require_chat_session_access


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _to_provider_parts(
    db: Session,
    user_id: str,
    parts: list,
    include_file_context: bool = True,
) -> list[ProviderMessagePart]:
    provider_parts: list[ProviderMessagePart] = []
    file_ids: list[str] = []

    for part in parts:
        if part.type == "text" and part.text:
            provider_parts.append(ProviderMessagePart(type="text", text=part.text))
        elif part.type == "image" and part.image_url:
            provider_parts.append(ProviderMessagePart(type="image", image_url=part.image_url))
        elif part.type == "file_ref" and part.file_id:
            file_ids.append(part.file_id)

    if include_file_context and file_ids:
        file_context = get_file_context_for_user(db, user_id, file_ids)
        if file_context:
            provider_parts.append(
                ProviderMessagePart(
                    type="file_ref",
                    file_text=f"Use this file context when answering:\n{file_context}",
                )
            )
    return provider_parts


def _assert_session_access(db: Session, session_id: str, user_id: str) -> ChatSession:
    chat_session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.deleted_at.is_(None))
        .first()
    )
    if not chat_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    require_chat_session_access(db, user_id, chat_session)
    return chat_session


async def stream_single_chat(
    db: Session,
    user_id: str,
    req: ChatStreamRequest,
) -> AsyncGenerator[str, None]:
    chat_session = _assert_session_access(db, req.session_id, user_id)
    assert_workspace_feature(db, chat_session.workspace_id, "file.analysis")

    user_text = "\n".join([p.text for p in req.parts if p.text])
    provider_parts = _to_provider_parts(db, user_id, req.parts)
    try:
        adapter = provider_registry.get_adapter(req.provider)
        api_key = provider_registry.resolve_api_key(
            db=db,
            user_id=user_id,
            provider=req.provider,
            key_mode=req.key_mode,
            local_api_key=req.local_api_key,
        )
    except HTTPException as exc:
        message = exc.detail if isinstance(exc.detail, str) else "Unable to resolve provider key"
        yield _sse({"type": "error", "message": message})
        return

    user_message = ChatMessage(
        session_id=req.session_id,
        role="user",
        provider=req.provider,
        model_id=req.model_id,
        content=user_text,
    )
    db.add(user_message)
    db.commit()

    assistant_text = ""
    yield _sse({"type": "start", "sessionId": req.session_id, "provider": req.provider, "modelId": req.model_id})

    try:
        async for chunk in adapter.stream_response(api_key, req.model_id, provider_parts):
            assistant_text += chunk.text
            yield _sse({"type": "delta", "text": chunk.text})
    except Exception as exc:
        yield _sse({"type": "error", "message": str(exc)})
        return

    assistant_message = ChatMessage(
        session_id=req.session_id,
        role="assistant",
        provider=req.provider,
        model_id=req.model_id,
        content=assistant_text,
        tokens_in=max(1, len(user_text.split())),
        tokens_out=max(1, len(assistant_text.split())),
    )
    db.add(assistant_message)
    db.commit()

    record_usage_event(
        db=db,
        user_id=user_id,
        workspace_id=chat_session.workspace_id,
        provider=req.provider,
        model_id=req.model_id,
        tokens_in=max(1, len(user_text.split())),
        tokens_out=max(1, len(assistant_text.split())),
        cost_usd=0.0,
    )
    yield _sse({"type": "done"})


async def stream_compare_chat(
    db: Session,
    user_id: str,
    req: CompareStreamRequest,
) -> AsyncGenerator[str, None]:
    chat_session = _assert_session_access(db, req.session_id, user_id)
    assert_workspace_feature(db, chat_session.workspace_id, "compare.mode")
    provider_parts = _to_provider_parts(db, user_id, req.parts)
    input_text = "\n".join([p.text for p in req.parts if p.text])

    queue: asyncio.Queue[tuple[str, str, str]] = asyncio.Queue()

    async def run_target(side: str, provider: Provider, model_id: str, key_mode: str, local_api_key: str | None) -> str:
        output = ""
        try:
            adapter = provider_registry.get_adapter(provider)
            api_key = provider_registry.resolve_api_key(
                db=db,
                user_id=user_id,
                provider=provider,
                key_mode=key_mode,
                local_api_key=local_api_key,
            )
            async for chunk in adapter.stream_response(api_key, model_id, provider_parts):
                output += chunk.text
                await queue.put((side, "delta", chunk.text))
            await queue.put((side, "done", ""))
        except HTTPException as exc:
            message = exc.detail if isinstance(exc.detail, str) else "Unable to resolve provider key"
            await queue.put((side, "error", message))
        except Exception as exc:
            await queue.put((side, "error", str(exc)))
        return output

    left_task = asyncio.create_task(
        run_target(
            "left",
            req.left.provider,
            req.left.model_id,
            req.left.key_mode,
            req.left.local_api_key,
        )
    )
    right_task = asyncio.create_task(
        run_target(
            "right",
            req.right.provider,
            req.right.model_id,
            req.right.key_mode,
            req.right.local_api_key,
        )
    )

    yield _sse({"type": "start", "sessionId": req.session_id})

    done_sides: set[str] = set()
    while len(done_sides) < 2:
        side, event_type, text = await queue.get()
        if event_type == "done":
            done_sides.add(side)
            yield _sse({"type": "done", "side": side})
        elif event_type == "error":
            done_sides.add(side)
            yield _sse({"type": "error", "side": side, "message": text})
        else:
            yield _sse({"type": "delta", "side": side, "text": text})

    left_output, right_output = await asyncio.gather(left_task, right_task)

    db.add(
        ChatMessage(
            session_id=req.session_id,
            role="user",
            content=input_text,
            provider=req.left.provider,
            model_id=req.left.model_id,
        )
    )
    db.add(
        ChatMessage(
            session_id=req.session_id,
            role="assistant",
            content=left_output,
            provider=req.left.provider,
            model_id=req.left.model_id,
            metadata_json={"side": "left"},
            tokens_in=max(1, len(input_text.split())),
            tokens_out=max(1, len(left_output.split())),
        )
    )
    db.add(
        ChatMessage(
            session_id=req.session_id,
            role="assistant",
            content=right_output,
            provider=req.right.provider,
            model_id=req.right.model_id,
            metadata_json={"side": "right"},
            tokens_in=max(1, len(input_text.split())),
            tokens_out=max(1, len(right_output.split())),
        )
    )
    db.commit()

    record_usage_event(
        db,
        user_id,
        chat_session.workspace_id,
        req.left.provider,
        req.left.model_id,
        max(1, len(input_text.split())),
        max(1, len(left_output.split())),
        0.0,
        event_type="chat.compare.left",
    )
    record_usage_event(
        db,
        user_id,
        chat_session.workspace_id,
        req.right.provider,
        req.right.model_id,
        max(1, len(input_text.split())),
        max(1, len(right_output.split())),
        0.0,
        event_type="chat.compare.right",
    )

    yield _sse({"type": "complete"})
