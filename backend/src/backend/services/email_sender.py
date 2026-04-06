"""Email delivery helpers for support replies."""

from __future__ import annotations

import json
import os
import smtplib
from typing import Any
from email.message import EmailMessage
from urllib import error, request


class SendGridEmailSender:
    """Support email sender: SMTP first, SendGrid as fallback."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        from_email: str | None = None,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        smtp_user: str | None = None,
        smtp_password: str | None = None,
        smtp_tls: bool | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("SENDGRID_API_KEY", "").strip()
        self.from_email = from_email or os.getenv(
            "SUPPORT_FROM_EMAIL",
            "support@vacancy-mirror.com",
        )
        self.smtp_host = (smtp_host or os.getenv("SMTP_HOST", "")).strip()
        self.smtp_port = int(smtp_port or os.getenv("SMTP_PORT", "587"))
        self.smtp_user = (smtp_user or os.getenv("SMTP_USER", "")).strip()
        self.smtp_password = (
            smtp_password or os.getenv("SMTP_PASSWORD", "")
        ).strip()
        smtp_tls_raw = (
            str(smtp_tls)
            if smtp_tls is not None
            else os.getenv("SMTP_TLS", "true")
        )
        self.smtp_tls = smtp_tls_raw.strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        self.timeout_seconds = timeout_seconds or int(
            os.getenv("SENDGRID_TIMEOUT_SECONDS", "15")
        )
        if not self.smtp_host and not self.api_key:
            raise ValueError("Configure SMTP_* or SENDGRID_API_KEY.")

    def send_support_reply(
        self,
        *,
        to_email: str,
        subject: str,
        text: str,
    ) -> None:
        """Send a plain-text email reply from support."""
        if self.smtp_host:
            self._send_via_smtp(
                to_email=to_email,
                subject=subject,
                text=text,
            )
            return
        self._send_via_sendgrid(
            to_email=to_email,
            subject=subject,
            text=text,
        )

    def _send_via_smtp(
        self,
        *,
        to_email: str,
        subject: str,
        text: str,
    ) -> None:
        """Send support reply via SMTP server."""
        if not self.smtp_user or not self.smtp_password:
            raise ValueError(
                "SMTP_USER and SMTP_PASSWORD are required for SMTP transport."
            )
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.from_email
        message["To"] = to_email
        message.set_content(text)

        with smtplib.SMTP(
            host=self.smtp_host,
            port=self.smtp_port,
            timeout=self.timeout_seconds,
        ) as client:
            if self.smtp_tls:
                client.starttls()
            client.login(self.smtp_user, self.smtp_password)
            client.send_message(message)

    def _send_via_sendgrid(
        self,
        *,
        to_email: str,
        subject: str,
        text: str,
    ) -> None:
        """Send support reply via SendGrid REST API."""
        if not self.api_key:
            raise ValueError("SENDGRID_API_KEY is required for SendGrid transport.")
        body: dict[str, Any] = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": self.from_email},
            "subject": subject,
            "content": [{"type": "text/plain", "value": text}],
        }
        req = request.Request(
            url="https://api.sendgrid.com/v3/mail/send",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds):
                return
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"SendGrid API error: {exc.code} {detail}"
            ) from exc

