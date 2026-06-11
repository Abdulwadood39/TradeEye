from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

from backend.app.core.config import get_settings

logger = logging.getLogger(__name__)


async def send_email(to_email: str, subject: str, html_body: str) -> bool:
    settings = get_settings()
    if not settings.smtp_host:
        logger.warning("SMTP not configured; email to %s skipped (dev mode)", to_email)
        logger.info("Email subject: %s", subject)
        return True

    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content("Please view this email in an HTML-capable client.")
    message.add_alternative(html_body, subtype="html")

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            start_tls=settings.smtp_use_tls,
        )
        return True
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)
        return False


async def send_verification_email(to_email: str, token: str) -> bool:
    settings = get_settings()
    url = f"{settings.frontend_url}/verify-email?token={token}"
    html = f"""
    <h2>Verify your TradeEye account</h2>
    <p>Click the link below to verify your email:</p>
    <p><a href="{url}">{url}</a></p>
    <p>This link expires in {settings.email_verification_expire_hours} hours.</p>
    """
    return await send_email(to_email, "Verify your TradeEye account", html)


async def send_password_reset_email(to_email: str, token: str) -> bool:
    settings = get_settings()
    url = f"{settings.frontend_url}/reset-password?token={token}"
    html = f"""
    <h2>Reset your TradeEye password</h2>
    <p>Click the link below to reset your password:</p>
    <p><a href="{url}">{url}</a></p>
    <p>This link expires in {settings.password_reset_expire_hours} hour(s).</p>
    """
    return await send_email(to_email, "Reset your TradeEye password", html)
