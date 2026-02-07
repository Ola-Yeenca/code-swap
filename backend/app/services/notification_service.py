from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

settings = get_settings()


class NotificationDeliveryResult(dict):
    @property
    def status(self) -> str:
        return str(self.get("status", "unknown"))


def _build_invite_url(token: str) -> str:
    base = settings.frontend_origin.rstrip("/")
    return f"{base}/invite/{token}"


def send_workspace_invite_email(
    recipient_email: str,
    workspace_name: str,
    inviter_email: str,
    invite_token: str,
) -> NotificationDeliveryResult:
    invite_url = _build_invite_url(invite_token)

    if not settings.smtp_host:
        return NotificationDeliveryResult(
            status="simulated",
            invite_url=invite_url,
            provider="console",
        )

    message = EmailMessage()
    message["Subject"] = f"Invitation to join {workspace_name}"
    message["From"] = settings.smtp_from_email or "no-reply@wrapper.local"
    message["To"] = recipient_email
    message.set_content(
        f"{inviter_email} invited you to join {workspace_name}.\n\n"
        f"Accept invite: {invite_url}\n"
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username and settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except Exception as exc:
        return NotificationDeliveryResult(
            status="failed",
            invite_url=invite_url,
            provider="smtp",
            error=str(exc),
        )

    return NotificationDeliveryResult(
        status="sent",
        invite_url=invite_url,
        provider="smtp",
    )
