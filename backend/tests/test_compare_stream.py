def test_compare_stream(client):
    headers = {"x-dev-user-email": "owner@example.com"}

    session_resp = client.post(
        "/v1/chat/sessions",
        headers=headers,
        json={"title": "Compare", "chatMode": "compare"},
    )
    assert session_resp.status_code == 200
    session_id = session_resp.json()["id"]

    payload = {
        "sessionId": session_id,
        "left": {
            "provider": "openai",
            "modelId": "gpt-5",
            "keyMode": "local",
            "localApiKey": "sk-left-123456789",
        },
        "right": {
            "provider": "anthropic",
            "modelId": "claude-sonnet-4-5",
            "keyMode": "local",
            "localApiKey": "sk-right-123456789",
        },
        "parts": [{"type": "text", "text": "Compare this"}],
    }

    with client.stream("POST", "/v1/compare/messages/stream", headers=headers, json=payload) as stream_resp:
        assert stream_resp.status_code == 200
        stream_text = "".join(chunk.decode("utf-8") for chunk in stream_resp.iter_bytes())

    assert '"type": "delta"' in stream_text
    assert '"side": "left"' in stream_text
    assert '"side": "right"' in stream_text
    assert '"type": "complete"' in stream_text


def test_compare_stream_missing_vault_keys_returns_error_events(client):
    headers = {"x-dev-user-email": "owner@example.com"}

    session_resp = client.post(
        "/v1/chat/sessions",
        headers=headers,
        json={"title": "Compare Missing Keys", "chatMode": "compare"},
    )
    assert session_resp.status_code == 200
    session_id = session_resp.json()["id"]

    payload = {
        "sessionId": session_id,
        "left": {
            "provider": "openai",
            "modelId": "gpt-5",
            "keyMode": "vault",
        },
        "right": {
            "provider": "anthropic",
            "modelId": "claude-sonnet-4-5",
            "keyMode": "vault",
        },
        "parts": [{"type": "text", "text": "Compare this"}],
    }

    with client.stream("POST", "/v1/compare/messages/stream", headers=headers, json=payload) as stream_resp:
        assert stream_resp.status_code == 200
        stream_text = "".join(chunk.decode("utf-8") for chunk in stream_resp.iter_bytes())

    assert '"type": "error"' in stream_text
    assert '"side": "left"' in stream_text
    assert '"side": "right"' in stream_text
    assert '"type": "complete"' in stream_text


def test_compare_stream_with_file_context(client):
    headers = {"x-dev-user-email": "owner@example.com"}

    session_resp = client.post(
        "/v1/chat/sessions",
        headers=headers,
        json={"title": "Compare File", "chatMode": "compare"},
    )
    assert session_resp.status_code == 200
    session_id = session_resp.json()["id"]

    file_resp = client.post(
        "/v1/files/presign-upload",
        headers=headers,
        json={
            "filename": "notes.txt",
            "mimeType": "text/plain",
            "sizeBytes": 64,
        },
    )
    assert file_resp.status_code == 200
    file_id = file_resp.json()["fileId"]

    ingest_resp = client.post(f"/v1/files/{file_id}/ingest", headers=headers)
    assert ingest_resp.status_code == 200

    payload = {
        "sessionId": session_id,
        "left": {
            "provider": "openai",
            "modelId": "gpt-5",
            "keyMode": "local",
            "localApiKey": "sk-left-123456789",
        },
        "right": {
            "provider": "anthropic",
            "modelId": "claude-sonnet-4-5",
            "keyMode": "local",
            "localApiKey": "sk-right-123456789",
        },
        "parts": [
            {"type": "text", "text": "Summarize attached file"},
            {"type": "file_ref", "fileId": file_id},
        ],
    }

    with client.stream("POST", "/v1/compare/messages/stream", headers=headers, json=payload) as stream_resp:
        assert stream_resp.status_code == 200
        stream_text = "".join(chunk.decode("utf-8") for chunk in stream_resp.iter_bytes())

    assert '"type": "delta"' in stream_text
    assert '"type": "complete"' in stream_text
