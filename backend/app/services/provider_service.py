from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import KeyCipher
from app.models import KeyMode, Provider, ProviderKey
from app.services.anthropic_adapter import AnthropicAdapter
from app.services.openai_adapter import OpenAIAdapter
from app.services.openrouter_adapter import OpenRouterAdapter
from app.services.providers_base import LLMProviderAdapter


class ProviderRegistry:
    def __init__(self) -> None:
        self._cipher = KeyCipher()
        self._adapters: dict[Provider, LLMProviderAdapter] = {
            Provider.OPENAI: OpenAIAdapter(),
            Provider.ANTHROPIC: AnthropicAdapter(),
            Provider.OPENROUTER: OpenRouterAdapter(),
        }

    def get_adapter(self, provider: Provider) -> LLMProviderAdapter:
        try:
            return self._adapters[provider]
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"Unsupported provider {provider}") from exc

    def resolve_api_key(
        self,
        db: Session,
        user_id: str,
        provider: Provider,
        key_mode: str,
        local_api_key: str | None = None,
    ) -> str:
        if key_mode == KeyMode.LOCAL:
            if not local_api_key:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="localApiKey is required when keyMode=local",
                )
            return local_api_key

        key_record = (
            db.query(ProviderKey)
            .filter(
                ProviderKey.user_id == user_id,
                ProviderKey.provider == provider,
                ProviderKey.key_mode == KeyMode.VAULT,
            )
            .order_by(ProviderKey.created_at.desc())
            .first()
        )
        if not key_record or not key_record.encrypted_api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"No vault key found for provider {provider.value}. "
                    "Add a vault key for this provider, switch key mode to local, "
                    "or select openrouter to use your OpenRouter key."
                ),
            )
        return self._cipher.decrypt(key_record.encrypted_api_key)


provider_registry = ProviderRegistry()
