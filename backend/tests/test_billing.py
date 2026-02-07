import pytest

from app.services import billing_service


@pytest.fixture(autouse=True)
def _billing_settings_guard():
    old_enabled = billing_service.settings.billing_enabled
    old_secret = billing_service.settings.stripe_secret_key
    old_webhook = billing_service.settings.stripe_webhook_secret
    old_price = billing_service.settings.stripe_price_id
    try:
        yield
    finally:
        billing_service.settings.billing_enabled = old_enabled
        billing_service.settings.stripe_secret_key = old_secret
        billing_service.settings.stripe_webhook_secret = old_webhook
        billing_service.settings.stripe_price_id = old_price


def test_billing_owner_checkout_and_status(client):
    billing_service.settings.billing_enabled = True
    billing_service.settings.stripe_secret_key = ""

    owner_headers = {"x-dev-user-email": "billing-owner@example.com"}
    ws_resp = client.post(
        "/v1/workspaces",
        headers=owner_headers,
        json={"name": "Billing Team", "dataRegion": "us"},
    )
    assert ws_resp.status_code == 200
    workspace_id = ws_resp.json()["id"]

    checkout_resp = client.post(
        "/v1/billing/checkout-session",
        headers=owner_headers,
        json={"workspaceId": workspace_id},
    )
    assert checkout_resp.status_code == 200
    payload = checkout_resp.json()
    assert payload["url"].startswith("https://checkout.stripe.com/pay/")
    assert payload["customerId"].startswith("cus_mock_")

    status_resp = client.get(
        "/v1/billing/status",
        headers=owner_headers,
        params={"workspaceId": workspace_id},
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["hasCustomer"] is True

    entitlements_resp = client.get(
        "/v1/billing/entitlements",
        headers=owner_headers,
        params={"workspaceId": workspace_id},
    )
    assert entitlements_resp.status_code == 200
    assert len(entitlements_resp.json()) >= 1


def test_billing_requires_owner(client):
    billing_service.settings.billing_enabled = True
    billing_service.settings.stripe_secret_key = ""

    owner_headers = {"x-dev-user-email": "billing-owner2@example.com"}
    ws_resp = client.post(
        "/v1/workspaces",
        headers=owner_headers,
        json={"name": "Billing Team 2", "dataRegion": "us"},
    )
    assert ws_resp.status_code == 200
    workspace_id = ws_resp.json()["id"]

    invite_resp = client.post(
        f"/v1/workspaces/{workspace_id}/invites",
        headers=owner_headers,
        json={"email": "billing-member@example.com", "role": "member"},
    )
    token = invite_resp.json()["token"]

    member_headers = {"x-dev-user-email": "billing-member@example.com"}
    client.post(f"/v1/invites/{token}/accept", headers=member_headers)

    checkout_resp = client.post(
        "/v1/billing/checkout-session",
        headers=member_headers,
        json={"workspaceId": workspace_id},
    )
    assert checkout_resp.status_code == 403
