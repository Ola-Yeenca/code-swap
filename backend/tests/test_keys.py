def test_create_vault_and_local_keys(client):
    headers = {"x-dev-user-email": "owner@example.com"}

    vault_resp = client.post(
        "/v1/keys",
        headers=headers,
        json={
            "provider": "openai",
            "keyMode": "vault",
            "apiKey": "sk-test-vault-12345678",
            "label": "OpenAI Vault",
        },
    )
    assert vault_resp.status_code == 200
    assert vault_resp.json()["keyMode"] == "vault"

    local_resp = client.post(
        "/v1/keys",
        headers=headers,
        json={
            "provider": "anthropic",
            "keyMode": "local",
            "apiKey": "sk-test-local-12345678",
            "label": "Anthropic Local",
        },
    )
    assert local_resp.status_code == 200
    assert local_resp.json()["keyMode"] == "local"

    openrouter_resp = client.post(
        "/v1/keys",
        headers=headers,
        json={
            "provider": "openrouter",
            "keyMode": "vault",
            "apiKey": "sk-or-v1-1234567890",
            "label": "OpenRouter Vault",
        },
    )
    assert openrouter_resp.status_code == 200
    assert openrouter_resp.json()["provider"] == "openrouter"

    list_resp = client.get("/v1/keys", headers=headers)
    assert list_resp.status_code == 200
    payload = list_resp.json()
    providers = {item["provider"] for item in payload}
    modes = {item["keyMode"] for item in payload}
    assert "openrouter" in providers
    assert "vault" in modes
    assert "local" in modes
