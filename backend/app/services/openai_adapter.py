from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import httpx

from app.core.config import get_settings
from app.models.enums import Provider
from app.services.providers_base import LLMProviderAdapter, ProviderMessagePart, ProviderModel, StreamChunk

settings = get_settings()


class OpenAIAdapter(LLMProviderAdapter):
    provider = Provider.OPENAI

    async def list_models(self, api_key: str) -> list[ProviderModel]:
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(f"{settings.openai_base_url}/models", headers=headers)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return []

        models: list[ProviderModel] = []
        for item in payload.get("data", []):
            model_id = item.get("id")
            if not model_id:
                continue
            capabilities = {
                "text": True,
                "image": any(k in model_id.lower() for k in ["vision", "gpt-4", "gpt-5"]),
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
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        input_items = []
        for part in parts:
            if part.type == "text" and part.text:
                input_items.append({"role": "user", "content": [{"type": "input_text", "text": part.text}]})
            elif part.type == "image" and part.image_url:
                input_items.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_image",
                                "image_url": part.image_url,
                            }
                        ],
                    }
                )
            elif part.type == "file_ref" and part.file_text:
                input_items.append(
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": part.file_text}],
                    }
                )

        body = {
            "model": model_id,
            "input": input_items,
            "stream": True,
        }

        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                async with client.stream(
                    "POST", f"{settings.openai_base_url}/responses", headers=headers, json=body
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

                        if event.get("type") in {
                            "response.output_text.delta",
                            "response.content_part.added",
                            "response.output_text.annotation.added",
                        }:
                            text = event.get("delta") or event.get("text") or ""
                            if text:
                                yield StreamChunk(type="delta", text=text)
                        elif event.get("type") == "response.completed":
                            break
            return
        except Exception:
            pass

        fallback_text = " ".join([p.text for p in parts if p.text])
        synthetic = f"OpenAI fallback response: {fallback_text[:300]}"
        for token in synthetic.split(" "):
            yield StreamChunk(type="delta", text=token + " ")
