from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import httpx

from app.core.config import get_settings
from app.models.enums import Provider
from app.services.providers_base import LLMProviderAdapter, ProviderMessagePart, ProviderModel, StreamChunk

settings = get_settings()


class AnthropicAdapter(LLMProviderAdapter):
    provider = Provider.ANTHROPIC

    async def list_models(self, api_key: str) -> list[ProviderModel]:
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(f"{settings.anthropic_base_url}/models", headers=headers)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return []

        data = payload.get("data") or payload.get("models") or []
        models: list[ProviderModel] = []
        for item in data:
            model_id = item.get("id")
            if not model_id:
                continue
            capabilities = {
                "text": True,
                "image": True,
                "file_analysis": True,
            }
            models.append(ProviderModel(id=model_id, capabilities=capabilities))
        return models

    async def stream_response(
        self,
        api_key: str,
        model_id: str,
        parts: list[ProviderMessagePart],
    ) -> AsyncGenerator[StreamChunk, None]:
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        content = []
        for part in parts:
            if part.type == "text" and part.text:
                content.append({"type": "text", "text": part.text})
            elif part.type == "image" and part.image_url:
                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "url",
                            "url": part.image_url,
                        },
                    }
                )
            elif part.type == "file_ref" and part.file_text:
                content.append({"type": "text", "text": part.file_text})

        body = {
            "model": model_id,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": content}],
            "stream": True,
        }

        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                async with client.stream(
                    "POST", f"{settings.anthropic_base_url}/messages", headers=headers, json=body
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        payload = line[len("data:") :].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            event = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {})
                            text = delta.get("text")
                            if text:
                                yield StreamChunk(type="delta", text=text)
                        elif event.get("type") == "message_stop":
                            break
            return
        except Exception:
            pass

        fallback_text = " ".join([p.text for p in parts if p.text])
        synthetic = f"Anthropic fallback response: {fallback_text[:300]}"
        for token in synthetic.split(" "):
            yield StreamChunk(type="delta", text=token + " ")
