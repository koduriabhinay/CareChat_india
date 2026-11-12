"""Sending email: sign-in codes and reminders.

"console" (development) only logs the email. "smtp" sends it through any
SMTP server, for example a free Zoho Mail or Gmail account with an app
password. Sending is done in a worker thread so the API stays responsive.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from .config import settings

log = logging.getLogger(__name__)

# The last email "sent" in console mode, so local testing can show sign-in codes.
outbox: list[dict[str, str]] = []


def _send_smtp(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


async def send_email(to: str, subject: str, body: str) -> bool:
    if settings.mail_backend == "smtp" and settings.smtp_host:
        try:
            await asyncio.to_thread(_send_smtp, to, subject, body)
            return True
        except (OSError, smtplib.SMTPException):
            log.exception("Email could not be sent")
            return False
    # Console mode: never log the address or body in production-like setups.
    outbox.append({"to": to, "subject": subject, "body": body})
    del outbox[:-20]
    log.info("Email (console mode) subject=%r", subject)
    return True
