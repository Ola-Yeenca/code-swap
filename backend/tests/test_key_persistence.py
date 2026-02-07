from app.models import KeyMode, ProviderKey


def test_local_key_not_persisted_encrypted(client, db_session):
    headers = {"x-dev-user-email": "persist@example.com"}
    response = client.post(
        "/v1/keys",
        headers=headers,
        json={
            "provider": "openai",
            "keyMode": "local",
            "apiKey": "sk-local-only-12345678",
        },
    )
    assert response.status_code == 200
    key_id = response.json()["id"]

    row = db_session.query(ProviderKey).filter(ProviderKey.id == key_id).first()
    assert row is not None
    assert row.key_mode == KeyMode.LOCAL
    assert row.encrypted_api_key is None
