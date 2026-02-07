def test_workspace_invite_accept(client):
    owner_headers = {"x-dev-user-email": "owner@example.com"}

    ws_resp = client.post(
        "/v1/workspaces",
        headers=owner_headers,
        json={"name": "Team One", "dataRegion": "us"},
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
    assert accept_resp.json()["ok"] is True
