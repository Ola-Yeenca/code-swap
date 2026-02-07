def test_chat_stream_and_usage(client):
    headers = {"x-dev-user-email": "owner@example.com"}

    session_resp = client.post(
        "/v1/chat/sessions",
        headers=headers,
        json={"title": "Test", "chatMode": "single"},
    )
    assert session_resp.status_code == 200
    session_id = session_resp.json()["id"]

    payload = {
        "sessionId": session_id,
        "provider": "openai",
        "modelId": "gpt-5",
        "keyMode": "local",
        "localApiKey": "sk-local-123456789",
        "parts": [{"type": "text", "text": "Say hello"}],
    }

    with client.stream("POST", "/v1/chat/messages/stream", headers=headers, json=payload) as stream_resp:
        assert stream_resp.status_code == 200
        stream_text = "".join(chunk.decode("utf-8") for chunk in stream_resp.iter_bytes())

    assert '"type": "delta"' in stream_text
    assert '"type": "done"' in stream_text

    usage_resp = client.get("/v1/usage/summary", headers=headers)
    assert usage_resp.status_code == 200
    summary = usage_resp.json()
    assert summary["totalRequests"] >= 1


def test_chat_stream_openrouter_route(client):
    headers = {"x-dev-user-email": "owner@example.com"}

    session_resp = client.post(
        "/v1/chat/sessions",
        headers=headers,
        json={"title": "OpenRouter Route", "chatMode": "single"},
    )
    assert session_resp.status_code == 200
    session_id = session_resp.json()["id"]

    payload = {
        "sessionId": session_id,
        "provider": "openrouter",
        "modelId": "openai/gpt-5",
        "keyMode": "local",
        "localApiKey": "sk-or-v1-test-123456789",
        "parts": [{"type": "text", "text": "Say router path works"}],
    }

    with client.stream("POST", "/v1/chat/messages/stream", headers=headers, json=payload) as stream_resp:
        assert stream_resp.status_code == 200
        stream_text = "".join(chunk.decode("utf-8") for chunk in stream_resp.iter_bytes())

    assert '"provider": "openrouter"' in stream_text
    assert '"type": "delta"' in stream_text
    assert '"type": "done"' in stream_text


def test_chat_stream_missing_vault_key_returns_error_event(client):
    headers = {"x-dev-user-email": "owner@example.com"}

    session_resp = client.post(
        "/v1/chat/sessions",
        headers=headers,
        json={"title": "Missing Vault Key", "chatMode": "single"},
    )
    assert session_resp.status_code == 200
    session_id = session_resp.json()["id"]

    payload = {
        "sessionId": session_id,
        "provider": "openai",
        "modelId": "gpt-5",
        "keyMode": "vault",
        "parts": [{"type": "text", "text": "Hello"}],
    }

    with client.stream("POST", "/v1/chat/messages/stream", headers=headers, json=payload) as stream_resp:
        assert stream_resp.status_code == 200
        stream_text = "".join(chunk.decode("utf-8") for chunk in stream_resp.iter_bytes())

    assert '"type": "error"' in stream_text
    assert "No vault key found for provider" in stream_text
