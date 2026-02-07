from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass

@dataclass
class ProviderMessagePart:
    type: str
    text: str | None = None
    image_url: str | None = None
    file_text: str | None = None


@dataclass
class StreamChunk:
    type: str
    text: str


@dataclass
class ProviderModel:
    id: str
    capabilities: dict


class LLMProviderAdapter(ABC):
    provider: str

    @abstractmethod
    async def list_models(self, api_key: str) -> list[ProviderModel]:
        raise NotImplementedError

    @abstractmethod
    async def stream_response(
        self,
        api_key: str,
        model_id: str,
        parts: list[ProviderMessagePart],
    ) -> AsyncGenerator[StreamChunk, None]:
        raise NotImplementedError
