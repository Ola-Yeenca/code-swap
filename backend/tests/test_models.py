from app.models import Provider
from app.services.provider_service import provider_registry
from app.services.providers_base import ProviderModel


class _FakeAdapter:
    def __init__(self, models: list[ProviderModel]) -> None:
        self._models = models

    async def list_models(self, api_key: str) -> list[ProviderModel]:
        return self._models


def test_refresh_and_list_models(client, monkeypatch):
    headers = {"x-dev-user-email": "owner@example.com"}

    client.post(
        "/v1/keys",
        headers=headers,
        json={"provider": "openai", "keyMode": "vault", "apiKey": "sk-openai-12345678"},
    )
    client.post(
        "/v1/keys",
        headers=headers,
        json={"provider": "anthropic", "keyMode": "vault", "apiKey": "sk-anthropic-12345678"},
    )
    client.post(
        "/v1/keys",
        headers=headers,
        json={"provider": "openrouter", "keyMode": "vault", "apiKey": "sk-or-v1-1234567890"},
    )

    monkeypatch.setitem(
        provider_registry._adapters,
        Provider.OPENAI,
        _FakeAdapter([ProviderModel(id="gpt-5", capabilities={"text": True})]),
    )
    monkeypatch.setitem(
        provider_registry._adapters,
        Provider.ANTHROPIC,
        _FakeAdapter([ProviderModel(id="claude-sonnet-4-5", capabilities={"text": True})]),
    )
    monkeypatch.setitem(
        provider_registry._adapters,
        Provider.OPENROUTER,
        _FakeAdapter([ProviderModel(id="openai/gpt-5", capabilities={"text": True})]),
    )

    refresh_resp = client.post("/v1/models/refresh", headers=headers)
    assert refresh_resp.status_code == 200
    assert refresh_resp.json()["ok"] is True
    assert refresh_resp.json()["stale"] is False

    models_resp = client.get("/v1/models", headers=headers)
    assert models_resp.status_code == 200
    data = models_resp.json()
    assert data["items"]

    openrouter_models_resp = client.get("/v1/models?provider=openrouter", headers=headers)
    assert openrouter_models_resp.status_code == 200
    openrouter_data = openrouter_models_resp.json()
    assert openrouter_data["items"]


def test_refresh_without_keys_reports_stale(client):
    headers = {"x-dev-user-email": "owner-no-keys@example.com"}
    refresh_resp = client.post("/v1/models/refresh", headers=headers)
    assert refresh_resp.status_code == 200
    assert refresh_resp.json()["stale"] is True
    assert "Missing vault key" in refresh_resp.json()["stale_reason"]
