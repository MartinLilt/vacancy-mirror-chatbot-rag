"""Chatwoot client for support inbox integration."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request


def _ticket_public_id(event_id: int) -> str:
    """Return VM-XXXXXX ticket ID using base-36 encoding (0-9, A-Z).

    Supports up to 2 176 782 335 unique ticket IDs (36^6 - 1).
    """
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    n = event_id
    digits: list[str] = []
    while n:
        digits.append(chars[n % 36])
        n //= 36
    b36 = "".join(reversed(digits)) if digits else "0"
    return f"VM-{b36.zfill(6)}"


class ChatwootSupportClient:
    """Minimal Chatwoot API client for creating support conversations."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        account_id: int | None = None,
        inbox_id: int | None = None,
        api_access_token: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.getenv("CHATWOOT_BASE_URL", "").strip()
        ).rstrip("/")
        self.account_id = account_id or int(
            os.getenv("CHATWOOT_ACCOUNT_ID", "0")
        )
        self.inbox_id = inbox_id or int(os.getenv("CHATWOOT_INBOX_ID", "0"))
        self.api_access_token = (
            api_access_token
            or os.getenv("CHATWOOT_API_ACCESS_TOKEN", "").strip()
        )
        self.timeout_seconds = timeout_seconds or int(
            os.getenv("CHATWOOT_TIMEOUT_SECONDS", "15")
        )

        if not self.base_url:
            raise ValueError("CHATWOOT_BASE_URL is required.")
        if self.account_id <= 0:
            raise ValueError("CHATWOOT_ACCOUNT_ID is required.")
        if self.inbox_id <= 0:
            raise ValueError("CHATWOOT_INBOX_ID is required.")
        if not self.api_access_token:
            raise ValueError("CHATWOOT_API_ACCESS_TOKEN is required.")

    def _api_url(self, path: str) -> str:
        return (
            f"{self.base_url}/api/v1/accounts/{self.account_id}/"
            f"{path.lstrip('/')}"
        )

    def _request_json(
        self,
        *,
        method: str,
        path: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        req = request.Request(
            url=self._api_url(path),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "api_access_token": self.api_access_token,
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
                if not body.strip():
                    return {}
                parsed = json.loads(body)
                if isinstance(parsed, dict):
                    return parsed
                raise RuntimeError("Chatwoot API returned non-object JSON.")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Chatwoot API error: {exc.code} {detail}"
            ) from exc

    def create_support_conversation(
        self,
        *,
        event_id: int,
        telegram_user_id: int,
        telegram_username: str,
        telegram_full_name: str,
        reply_channel: str,
        feedback_message: str,
        reply_email: str = "",
    ) -> dict[str, Any]:
        """Create Chatwoot contact + conversation + incoming message."""
        contact_payload: dict[str, Any] = {
            "name": telegram_full_name or f"Telegram user {telegram_user_id}",
            "inbox_id": self.inbox_id,
            "custom_attributes": {
                "telegram_user_id": str(telegram_user_id),
                "telegram_username": telegram_username,
            },
        }
        if reply_email:
            contact_payload["email"] = reply_email
            contact_payload["custom_attributes"]["reply_email"] = reply_email

        contact = self._request_json(
            method="POST",
            path="contacts",
            payload=contact_payload,
        )
        contact_id_raw = contact.get("id", 0)
        if not contact_id_raw:
            payload = contact.get("payload")
            if isinstance(payload, dict):
                contact_obj = payload.get("contact")
                if isinstance(contact_obj, dict):
                    contact_id_raw = contact_obj.get("id", 0)
        contact_id = int(contact_id_raw or 0)
        if contact_id <= 0:
            raise RuntimeError("Chatwoot contact creation failed.")

        source_id = ""
        payload = contact.get("payload")
        if isinstance(payload, dict):
            contact_inbox = payload.get("contact_inbox")
            if isinstance(contact_inbox, dict):
                source_id = str(contact_inbox.get("source_id", "")).strip()

        conversation = self._request_json(
            method="POST",
            path="conversations",
            payload={
                "contact_id": contact_id,
                "inbox_id": self.inbox_id,
                "source_id": source_id,
                "status": "open",
                "custom_attributes": {
                    "support_event_id": str(event_id),
                    "reply_channel": reply_channel,
                    "telegram_user_id": str(telegram_user_id),
                    "telegram_username": telegram_username,
                    "reply_email": reply_email,
                },
            },
        )
        conversation_id = int(conversation.get("id", 0))
        if conversation_id <= 0:
            raise RuntimeError("Chatwoot conversation creation failed.")

        public_ticket_id = _ticket_public_id(event_id)

        details = [
            f"Support event ID: {event_id}",
            f"Public ticket ID: {public_ticket_id}",
            f"Reply channel: {reply_channel}",
            f"Telegram user ID: {telegram_user_id}",
            f"Telegram username: {telegram_username or '—'}",
        ]
        if reply_email:
            details.append(f"Reply email: {reply_email}")
        details.extend([
            "",
            "Operator notes:",
            "- Send a PUBLIC reply to deliver message to user.",
            "- Add PRIVATE note `/end ticket ...` to close ticket and notify user.",
        ])
        content = (
            "New support request from Telegram bot.\n\n"
            + "\n".join(details)
            + "\n\n"
            + "Message:\n"
            + feedback_message.strip()
        )

        self._request_json(
            method="POST",
            path=f"conversations/{conversation_id}/messages",
            payload={
                "content": content,
                "message_type": "incoming",
                "private": False,
            },
        )
        return {
            "contact_id": contact_id,
            "conversation_id": conversation_id,
        }

