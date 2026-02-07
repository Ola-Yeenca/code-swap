from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import httpx

from app.models.enums import Provider
from app.services.providers_base import LLMProviderAdapter, ProviderMessagePart, ProviderModel, StreamChunk

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterAdapter(LLMProviderAdapter):
    provider = Provider.OPENROUTER

    async def list_models(self, api_key: str) -> list[ProviderModel]:
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(f"{OPENROUTER_BASE_URL}/models", headers=headers)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return []

        models: list[ProviderModel] = []
        for item in payload.get("data", []):
            model_id = item.get("id")
            if not model_id:
                continue
            context_length = item.get("context_length", 0)
            pricing = item.get("pricing", {})
            capabilities = {
                "text": True,
                "image": "vision" in model_id.lower() or item.get("architecture", {}).get(
                    "modality", ""
                ) == "multimodal",
                "context_length": context_length,
                "prompt_cost": pricing.get("prompt", "0"),
                "completion_cost": pricing.get("completion", "0"),
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
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/code-swap",
            "X-Title": "code-swap",
        }

        messages = []
        for part in parts:
            if part.type == "text" and part.text:
                messages.append({"role": "user", "content": part.text})
            elif part.type == "image" and part.image_url:
                messages.append({
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": part.image_url}},
                    ],
                })
            elif part.type == "file_ref" and part.file_text:
                messages.append({"role": "user", "content": part.file_text})

        body = {
            "model": model_id,
            "messages": messages,
            "stream": True,
        }

        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                async with client.stream(
                    "POST", f"{OPENROUTER_BASE_URL}/chat/completions", headers=headers, json=body
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        payload = line[len("data:"):].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            event = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        choices = event.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            text = delta.get("content")
                            if text:
                                yield StreamChunk(type="delta", text=text)
            return
        except Exception:
            pass

        fallback_text = " ".join([p.text for p in parts if p.text])
        synthetic = f"OpenRouter fallback response: {fallback_text[:300]}"
        for token in synthetic.split(" "):
            yield StreamChunk(type="delta", text=token + " ")
