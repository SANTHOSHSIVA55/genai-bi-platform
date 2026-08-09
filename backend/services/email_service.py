"""Email delivery service.

Sends transactional emails via SMTP when configured (SMTP_HOST set). Falls back
to writing the email contents to the application log so the application works
in local development and in tests without an SMTP server.
"""
import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Optional

logger = logging.getLogger("app.email")

APP_NAME = os.getenv("APP_NAME", "GenAI BI Platform")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


def _smtp_configured() -> bool:
    return bool(os.getenv("SMTP_HOST"))


def _send_smtp(subject: str, to_email: str, text: str, html: Optional[str] = None) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.getenv("SMTP_FROM", f"{APP_NAME} <noreply@example.com>")
    msg["To"] = to_email
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")

    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=15) as server:
        server.ehlo()
        if os.getenv("SMTP_TLS", "true").lower() != "false":
            server.starttls()
        username = os.getenv("SMTP_USER")
        password = os.getenv("SMTP_PASSWORD")
        if username and password:
            server.login(username, password)
        server.send_message(msg)


def send_mail(
    subject: str,
    to_email: str,
    text: str,
    html: Optional[str] = None,
) -> bool:
    """Deliver an email. Returns True when handed off to SMTP or logged."""
    try:
        if _smtp_configured():
            _send_smtp(subject, to_email, text, html)
            logger.info("Email sent to %s: %s", to_email, subject)
        else:
            logger.info("[EMAIL OUTBOX] To: %s | Subject: %s\n%s", to_email, subject, text)
        return True
    except Exception as exc:  # pragma: no cover - depends on external infra
        logger.error("Failed to send email to %s: %s", to_email, exc)
        return False


def send_verification_email(to_email: str, token: str) -> bool:
    url = f"{FRONTEND_URL}/verify-email?token={token}"
    subject = f"Verify your {APP_NAME} account"
    text = (
        f"Welcome to {APP_NAME}!\n\n"
        f"Please verify your email address by visiting:\n{url}\n\n"
        f"This link expires in 24 hours.\n"
    )
    return send_mail(subject, to_email, text)


def send_password_reset_email(to_email: str, token: str) -> bool:
    url = f"{FRONTEND_URL}/reset-password?token={token}"
    subject = f"Reset your {APP_NAME} password"
    text = (
        f"A password reset was requested for your {APP_NAME} account.\n\n"
        f"Reset your password by visiting:\n{url}\n\n"
        f"This link expires in 60 minutes. If you did not request this, "
        f"you can safely ignore this email.\n"
    )
    return send_mail(subject, to_email, text)
