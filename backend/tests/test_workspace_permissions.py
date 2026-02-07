def test_workspace_shared_session_access(client):
    owner_headers = {"x-dev-user-email": "owner@example.com"}

    ws_resp = client.post(
        "/v1/workspaces",
        headers=owner_headers,
        json={"name": "Team", "dataRegion": "us"},
    )
    assert ws_resp.status_code == 200
    workspace_id = ws_resp.json()["id"]

    invite_resp = client.post(
        f"/v1/workspaces/{workspace_id}/invites",
        headers=owner_headers,
        json={"email": "member@example.com", "role": "member"},
    )
    assert invite_resp.status_code == 200
    token = invite_resp.json()["token"]

    member_headers = {"x-dev-user-email": "member@example.com"}
    accept_resp = client.post(f"/v1/invites/{token}/accept", headers=member_headers)
    assert accept_resp.status_code == 200

    session_resp = client.post(
        "/v1/chat/sessions",
        headers=owner_headers,
        json={"title": "Shared", "chatMode": "single", "workspaceId": workspace_id},
    )
    assert session_resp.status_code == 200
    session_id = session_resp.json()["id"]

    member_get = client.get(f"/v1/chat/sessions/{session_id}", headers=member_headers)
    assert member_get.status_code == 200

    outsider_headers = {"x-dev-user-email": "outsider@example.com"}
    outsider_get = client.get(f"/v1/chat/sessions/{session_id}", headers=outsider_headers)
    assert outsider_get.status_code == 404


def test_workspace_invite_resend_revoke(client):
    owner_headers = {"x-dev-user-email": "owner2@example.com"}

    ws_resp = client.post(
        "/v1/workspaces",
        headers=owner_headers,
        json={"name": "Team Two", "dataRegion": "us"},
    )
    assert ws_resp.status_code == 200
    workspace_id = ws_resp.json()["id"]

    invite_resp = client.post(
        f"/v1/workspaces/{workspace_id}/invites",
        headers=owner_headers,
        json={"email": "member2@example.com", "role": "member"},
    )
    assert invite_resp.status_code == 200
    invite_id = invite_resp.json()["id"]

    resend_resp = client.post(
        f"/v1/workspaces/{workspace_id}/invites/{invite_id}/resend",
        headers=owner_headers,
    )
    assert resend_resp.status_code == 200

    revoke_resp = client.delete(
        f"/v1/workspaces/{workspace_id}/invites/{invite_id}",
        headers=owner_headers,
    )
    assert revoke_resp.status_code == 200

    list_resp = client.get(f"/v1/workspaces/{workspace_id}/invites", headers=owner_headers)
    assert list_resp.status_code == 200
    assert all(item["id"] != invite_id for item in list_resp.json())
