"""Email delivery helpers for support replies."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request


class SendGridEmailSender:
    """Minimal SendGrid sender using REST API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        from_email: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("SENDGRID_API_KEY", "").strip()
        self.from_email = from_email or os.getenv(
            "SUPPORT_FROM_EMAIL",
            "support@vacancy-mirror.com",
        )
        self.timeout_seconds = timeout_seconds or int(
            os.getenv("SENDGRID_TIMEOUT_SECONDS", "15")
        )
        if not self.api_key:
            raise ValueError("SENDGRID_API_KEY is required.")

    def send_support_reply(
        self,
        *,
        to_email: str,
        subject: str,
        text: str,
    ) -> None:
        """Send a plain-text email reply from support."""
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

