"""Stripe webhook HTTP server for subscription management.

Listens for Stripe ``checkout.session.completed`` and
``customer.subscription.deleted`` events, writes the result to
the ``subscriptions`` table, and notifies the Telegram user.

Environment variables
---------------------
STRIPE_WEBHOOK_SECRET : str
    Webhook signing secret from the Stripe Dashboard
    (Developers → Webhooks → signing secret).
TELEGRAM_BOT_TOKEN : str
    Bot token used to send confirmation messages.
WEBHOOK_PORT : int, optional
    Port to listen on. Default: 8080.
DB_URL : str
    PostgreSQL connection URL.
"""

from __future__ import annotations

import hashlib
import hmac
import http.server
import json
import logging
import os
import threading
import urllib.request
import urllib.parse
from typing import Any

from backend.services.email_sender import SendGridEmailSender
from backend.services.google_sheets import (
    GoogleSheetsService,
    build_user_row,
)
from backend.services.postgres import PostgresJobExportService

log = logging.getLogger(__name__)
_SUPPORT_UNPIN_FAILED_MARKER = "SUPPORT_TICKET_UNPIN_FAILED"

# Plan name mapping from Stripe product/price metadata to internal name
_PLAN_BY_STRIPE_PRICE: dict[str, str] = {}  # populated at runtime

# Maps Stripe Price IDs to plan names.
# Set STRIPE_PRICE_PLUS and STRIPE_PRICE_PRO_PLUS env vars.
_PLAN_ENV_MAP: dict[str, str] = {
    "STRIPE_PRICE_PLUS": "plus",
    "STRIPE_PRICE_PRO_PLUS": "pro_plus",
}


def _plan_from_session(session: dict[str, Any]) -> str:
    """Resolve plan name from a Stripe checkout session.

    Checks ``metadata.plan`` first, then falls back to matching
    the price ID against env-configured price IDs.

    Args:
        session: Stripe checkout.session object dict.

    Returns:
        Plan name string: 'plus' or 'pro_plus'.
        Falls back to 'plus' if unable to determine.
    """
    # Prefer explicit metadata set on the Payment Link
    meta = session.get("metadata") or {}
    if meta.get("plan"):
        return meta["plan"]

    # Fall back to price ID matching
    price_id = ""
    line_items = session.get("line_items", {})
    data = line_items.get("data") if isinstance(
        line_items, dict
    ) else []
    if data:
        price_id = (
            data[0].get("price", {}).get("id", "")
        )

    for env_key, plan_name in _PLAN_ENV_MAP.items():
        configured = os.environ.get(env_key, "").strip()
        if configured and configured == price_id:
            return plan_name

    log.warning(
        "Cannot determine plan from session %s, defaulting to plus.",
        session.get("id"),
    )
    return "plus"


def _send_telegram_message(
    token: str,
    chat_id: int,
    text: str,
    *,
    raise_on_error: bool = False,
) -> None:
    """Send a plain-text Telegram message via Bot API.

    Args:
        token: Bot token.
        chat_id: Telegram chat/user ID.
        text: Message text (plain, no parse_mode).
    """
    url = (
        f"https://api.telegram.org/bot{token}/sendMessage"
    )
    payload = json.dumps(
        {"chat_id": chat_id, "text": text}
    ).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            log.debug(
                "Telegram sendMessage status: %s", resp.status
            )
    except Exception as exc:
        log.exception(
            "Failed to send Telegram message to %s: %s",
            chat_id, exc,
        )
        if raise_on_error:
            raise


def _unpin_telegram_message(
    token: str,
    chat_id: int,
    message_id: int,
    *,
    raise_on_error: bool = False,
) -> bool:
    """Unpin one Telegram message by message_id.

    Returns:
        True when unpin succeeds or when message_id is not set.
        False when Telegram API call fails.
    """
    if message_id <= 0:
        return True
    url = f"https://api.telegram.org/bot{token}/unpinChatMessage"
    payload = json.dumps(
        {"chat_id": chat_id, "message_id": message_id}
    ).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            log.debug("Telegram unpinChatMessage status: %s", resp.status)
            return True
    except Exception as exc:
        log.warning(
            "Failed to unpin Telegram message %s for chat %s: %s",
            message_id,
            chat_id,
            exc,
        )
        if raise_on_error:
            raise
        return False


def _verify_stripe_signature(
    payload: bytes,
    sig_header: str,
    secret: str,
) -> bool:
    """Verify Stripe webhook signature (HMAC-SHA256).

    Args:
        payload: Raw request body bytes.
        sig_header: Value of the Stripe-Signature HTTP header.
        secret: Webhook signing secret.

    Returns:
        True if signature is valid.
    """
    try:
        parts = {
            k: v
            for item in sig_header.split(",")
            for k, v in [item.split("=", 1)]
        }
        timestamp = parts.get("t", "")
        signature = parts.get("v1", "")
        signed = f"{timestamp}.".encode() + payload
        # Stripe signing secret is prefixed with "whsec_";
        # only the raw bytes after the prefix are used as key.
        raw_secret = secret.removeprefix("whsec_")
        expected = hmac.new(
            raw_secret.encode(), signed, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False


def _to_base36(n: int) -> str:
    """Convert a non-negative integer to a base-36 string (digits 0-9, letters A-Z).

    Base-36 gives 36^6 = 2 176 782 336 unique values with 6 characters,
    vs only 1 000 000 with plain decimal.
    """
    if n < 0:
        raise ValueError("n must be non-negative")
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if n == 0:
        return "0"
    result: list[str] = []
    while n:
        result.append(chars[n % 36])
        n //= 36
    return "".join(reversed(result))


def _support_ticket_public_id(event_id: int) -> str:
    """Build user-facing support ticket ID from internal event ID.

    Format: VM-XXXXXX where X is a base-36 character (0-9 / A-Z).
    Supports up to 2 176 782 335 tickets (36^6 - 1).
    Examples:
        event_id=1      → VM-000001
        event_id=9      → VM-000009
        event_id=10     → VM-00000A
        event_id=999999 → VM-00LFLR
    """
    return f"VM-{_to_base36(event_id).zfill(6)}"


def _support_reply_telegram_text(*, event_id: int, answer: str) -> str:
    """Render support reply text sent to Telegram users."""
    return (
        "🆘 Support reply from Vacancy Mirror:\n\n"
        f"Ticket: {_support_ticket_public_id(event_id)}\n\n"
        "Answer:\n"
        f"{answer.strip()}"
    )


def _support_ticket_closed_telegram_text(*, event_id: int) -> str:
    """Render support ticket closed notification for Telegram users."""
    return (
        "✅ Support ticket closed.\n\n"
        f"Ticket: {_support_ticket_public_id(event_id)}"
    )


def _support_ticket_unpin_failed_telegram_text(*, event_id: int) -> str:
    """Render fallback text when pinned ticket message could not be unpinned."""
    return (
        "ℹ️ Ticket closed, but I could not unpin the original ticket message automatically.\n"
        "Please unpin it manually if needed.\n\n"
        f"Ticket: {_support_ticket_public_id(event_id)}"
    )


class _WebhookHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for Stripe webhook events."""

    db: PostgresJobExportService
    sheets: GoogleSheetsService
    token: str
    secret: str
    stripe_plus_url: str
    stripe_pro_plus_url: str
    support_api_token: str
    chatwoot_webhook_token: str

    def _json_response(
        self,
        *,
        status: int,
        payload: dict[str, Any],
    ) -> None:
        """Write a JSON response with common headers."""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        """Parse request body as JSON object."""
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("JSON body must be an object.")
        return parsed

    def _is_support_authorized(self) -> bool:
        """Validate support API token from Authorization header."""
        token = self.support_api_token.strip()
        if not token:
            return False
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False
        return hmac.compare_digest(
            auth_header.removeprefix("Bearer ").strip(),
            token,
        )

    def _is_chatwoot_authorized(self) -> bool:
        """Validate Chatwoot webhook token header."""
        token = self.chatwoot_webhook_token.strip()
        if not token:
            return False
        incoming = self.headers.get("X-Chatwoot-Token", "").strip()
        if incoming and hmac.compare_digest(incoming, token):
            return True
        parsed = urllib.parse.urlparse(self.path)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        query_token = str(params.get("token", "")).strip()
        if query_token and hmac.compare_digest(query_token, token):
            return True
        return False

    @staticmethod
    def _chatwoot_message_content(payload: dict[str, Any]) -> str:
        """Extract textual content from Chatwoot webhook payload."""
        content = payload.get("content")
        if isinstance(content, str):
            return content.strip()
        message = payload.get("message")
        if isinstance(message, dict):
            nested = message.get("content")
            if isinstance(nested, str):
                return nested.strip()
        return ""

    @staticmethod
    def _chatwoot_conversation_id(payload: dict[str, Any]) -> int:
        """Extract conversation ID from Chatwoot webhook payload."""
        conversation = payload.get("conversation")
        if isinstance(conversation, dict):
            try:
                return int(conversation.get("id", 0))
            except Exception:  # noqa: BLE001
                return 0
        try:
            return int(payload.get("conversation_id", 0))
        except Exception:  # noqa: BLE001
            return 0

    @staticmethod
    def _chatwoot_message_id(payload: dict[str, Any]) -> str:
        """Extract message ID for idempotency checks."""
        value = payload.get("id")
        if value is None:
            message = payload.get("message")
            if isinstance(message, dict):
                value = message.get("id")
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _chatwoot_is_public_agent_reply(payload: dict[str, Any]) -> bool:
        """Return True only for public outgoing agent replies."""
        if bool(payload.get("private", False)):
            return False
        event_name = str(payload.get("event", "")).strip().lower()
        if event_name and event_name != "message_created":
            return False

        message_type = payload.get("message_type")
        if isinstance(message_type, str):
            value = message_type.strip().lower()
            if value not in {"outgoing", "agent"}:
                return False
        elif message_type is not None:
            try:
                # Chatwoot can send integer message type where 1 is outgoing.
                if int(message_type) != 1:
                    return False
            except Exception:  # noqa: BLE001
                return False

        sender = payload.get("sender")
        if isinstance(sender, dict):
            sender_type = str(sender.get("type", "")).strip().lower()
            if sender_type and sender_type not in {"user", "agent"}:
                return False
        return True

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """Strip common Markdown inline formatting added by Chatwoot (bold, italic, code)."""
        import re
        # Remove bold (**text** or __text__), italic (*text* or _text_), inline code (`text`)
        text = re.sub(r"\*{1,2}(.*?)\*{1,2}", r"\1", text)
        text = re.sub(r"_{1,2}(.*?)_{1,2}", r"\1", text)
        text = re.sub(r"`(.*?)`", r"\1", text)
        return text

    @staticmethod
    def _chatwoot_is_private_close_command(payload: dict[str, Any]) -> bool:
        """Return True for private notes that close a support ticket."""
        if not bool(payload.get("private", False)):
            return False
        content = _WebhookHandler._chatwoot_message_content(payload)
        # Chatwoot may render Markdown in private notes (e.g. /end ticket → **/end ticket**)
        # so strip inline Markdown before matching the command prefix.
        clean = _WebhookHandler._strip_markdown(content).strip().lower()
        return clean.startswith("/end ticket")

    def _resolve_feedback_event_from_chatwoot(
        self,
        *,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Resolve support event by Chatwoot conversation or custom event id."""
        conversation_id = self._chatwoot_conversation_id(payload)
        if conversation_id > 0:
            event = self.db.get_support_feedback_event_by_chatwoot_conversation(
                conversation_id=conversation_id,
            )
            if event:
                return event

        conversation = payload.get("conversation")
        if isinstance(conversation, dict):
            custom = conversation.get("custom_attributes")
            if isinstance(custom, dict):
                event_id_raw = custom.get("support_event_id")
                try:
                    event_id = int(str(event_id_raw).strip())
                except Exception:  # noqa: BLE001
                    event_id = 0
                if event_id > 0:
                    return self.db.get_support_feedback_event(event_id=event_id)
        return None

    def log_message(  # type: ignore[override]
        self, format: str, *args: Any
    ) -> None:
        """Suppress default access log; use Python logging."""
        log.debug(format, *args)

    def do_GET(self) -> None:  # noqa: N802
        """Handle GET /pay/plus and /pay/pro-plus.

        Redirects to Stripe Payment Link, appending
        ``client_reference_id`` from the ``uid`` query param.
        This keeps the Telegram button URL clean (no long params).
        """
        parsed = urllib.parse.urlparse(self.path)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        uid = params.get("uid", "")

        if parsed.path == "/support/inbox":
            if not self._is_support_authorized():
                self._json_response(
                    status=401,
                    payload={"ok": False, "error": "unauthorized"},
                )
                return
            status = params.get("status", "").strip() or None
            limit_raw = params.get("limit", "200").strip()
            try:
                limit = int(limit_raw)
            except ValueError:
                self._json_response(
                    status=400,
                    payload={"ok": False, "error": "invalid_limit"},
                )
                return
            rows = self.db.get_support_feedback_inbox(
                status=status,
                limit=limit,
            )
            self._json_response(status=200, payload={"ok": True, "items": rows})
            return

        if parsed.path.startswith("/support/inbox/"):
            if not self._is_support_authorized():
                self._json_response(
                    status=401,
                    payload={"ok": False, "error": "unauthorized"},
                )
                return
            event_id_raw = parsed.path.removeprefix("/support/inbox/").strip("/")
            try:
                event_id = int(event_id_raw)
            except ValueError:
                self._json_response(
                    status=400,
                    payload={"ok": False, "error": "invalid_event_id"},
                )
                return
            event = self.db.get_support_feedback_event(event_id=event_id)
            if not event:
                self._json_response(
                    status=404,
                    payload={"ok": False, "error": "not_found"},
                )
                return
            self._json_response(status=200, payload={"ok": True, "item": event})
            return

        if parsed.path == "/pay/plus":
            base = self.stripe_plus_url
        elif parsed.path == "/pay/pro-plus":
            base = self.stripe_pro_plus_url
        else:
            self.send_response(404)
            self.end_headers()
            return

        if uid:
            target = f"{base}?client_reference_id={uid}"
        else:
            target = base

        self.send_response(302)
        self.send_header("Location", target)
        self.end_headers()
        log.info(
            "Redirecting uid=%s to %s", uid, parsed.path
        )

    def do_POST(self) -> None:  # noqa: N802
        """Handle POST /webhook from Stripe."""
        request_path = urllib.parse.urlparse(self.path).path

        if request_path == "/support/chatwoot/webhook":
            if not self._is_chatwoot_authorized():
                self._json_response(
                    status=401,
                    payload={"ok": False, "error": "unauthorized"},
                )
                return
            try:
                body = self._read_json_body()
            except Exception as exc:  # noqa: BLE001
                self._json_response(
                    status=400,
                    payload={"ok": False, "error": f"invalid_json: {exc}"},
                )
                return

            message_id = self._chatwoot_message_id(body)

            if self._chatwoot_is_private_close_command(body):
                if (
                    message_id
                    and self.db.support_reply_exists_by_external_message_id(
                        external_message_id=message_id
                    )
                ):
                    self._json_response(
                        status=200,
                        payload={"ok": True, "ignored": "duplicate_message"},
                    )
                    return

                event = self._resolve_feedback_event_from_chatwoot(payload=body)
                if not event:
                    self._json_response(
                        status=404,
                        payload={"ok": False, "error": "support_event_not_found"},
                    )
                    return

                event_id = int(event["id"])
                sender = body.get("sender")
                operator_name = ""
                if isinstance(sender, dict):
                    operator_name = str(sender.get("name", "")).strip()

                channel = str(event.get("reply_channel", "")).strip().lower()
                sent_to = ""
                try:
                    if channel == "telegram":
                        chat_id = int(event["telegram_user_id"])
                        telegram_message_id = int(
                            event.get("telegram_message_id", 0) or 0
                        )
                        _send_telegram_message(
                            token=self.token,
                            chat_id=chat_id,
                            text=_support_ticket_closed_telegram_text(
                                event_id=event_id,
                            ),
                            raise_on_error=True,
                        )
                        unpinned = _unpin_telegram_message(
                            token=self.token,
                            chat_id=chat_id,
                            message_id=telegram_message_id,
                        )
                        if not unpinned:
                            log.warning(
                                "%s event_id=%s chat_id=%s telegram_message_id=%s chatwoot_message_id=%s",
                                _SUPPORT_UNPIN_FAILED_MARKER,
                                event_id,
                                chat_id,
                                telegram_message_id,
                                message_id,
                            )
                            _send_telegram_message(
                                token=self.token,
                                chat_id=chat_id,
                                text=_support_ticket_unpin_failed_telegram_text(
                                    event_id=event_id,
                                ),
                            )
                        sent_to = str(chat_id)

                    self.db.upsert_support_feedback_status(
                        event_id=event_id,
                        status="closed",
                        assigned_to=operator_name,
                    )

                    if channel in {"telegram", "email"}:
                        self.db.insert_support_reply(
                            feedback_event_id=event_id,
                            channel=channel,
                            sent_to=sent_to,
                            reply_text="Ticket closed by support.",
                            operator_name=operator_name,
                            status="sent",
                            source="chatwoot",
                            external_message_id=message_id,
                        )

                    self._json_response(
                        status=200,
                        payload={
                            "ok": True,
                            "event_id": event_id,
                            "status": "closed",
                            "sent_to": sent_to,
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    if channel in {"telegram", "email"}:
                        self.db.insert_support_reply(
                            feedback_event_id=event_id,
                            channel=channel,
                            sent_to=sent_to,
                            reply_text="Ticket closed by support.",
                            operator_name=operator_name,
                            status="failed",
                            source="chatwoot",
                            external_message_id=message_id,
                            error_message=str(exc),
                        )
                    self._json_response(
                        status=500,
                        payload={"ok": False, "error": f"close_failed: {exc}"},
                    )
                return

            if not self._chatwoot_is_public_agent_reply(body):
                self._json_response(
                    status=200,
                    payload={"ok": True, "ignored": "not_agent_public_reply"},
                )
                return
            if (
                message_id
                and self.db.support_reply_exists_by_external_message_id(
                    external_message_id=message_id
                )
            ):
                self._json_response(
                    status=200,
                    payload={"ok": True, "ignored": "duplicate_message"},
                )
                return

            event = self._resolve_feedback_event_from_chatwoot(payload=body)
            if not event:
                self._json_response(
                    status=404,
                    payload={"ok": False, "error": "support_event_not_found"},
                )
                return

            event_id = int(event["id"])
            reply_text = self._chatwoot_message_content(body)
            if not reply_text:
                self._json_response(
                    status=400,
                    payload={"ok": False, "error": "reply_text_required"},
                )
                return

            sender = body.get("sender")
            operator_name = ""
            if isinstance(sender, dict):
                operator_name = str(sender.get("name", "")).strip()
            channel = str(event.get("reply_channel", "")).strip().lower()
            sent_to = ""
            try:
                if channel == "telegram":
                    chat_id = int(event["telegram_user_id"])
                    _send_telegram_message(
                        token=self.token,
                        chat_id=chat_id,
                        text=_support_reply_telegram_text(
                            event_id=event_id,
                            answer=reply_text,
                        ),
                        raise_on_error=True,
                    )
                    sent_to = str(chat_id)
                elif channel == "email":
                    to_email = str(event.get("reply_email", "")).strip()
                    if not to_email:
                        self._json_response(
                            status=400,
                            payload={"ok": False, "error": "reply_email_missing_for_event"},
                        )
                        return
                    sender_email = SendGridEmailSender()
                    sender_email.send_support_reply(
                        to_email=to_email,
                        subject="Vacancy Mirror Support Reply",
                        text=reply_text,
                    )
                    sent_to = to_email
                else:
                    self._json_response(
                        status=200,
                        payload={"ok": True, "ignored": "no_reply_requested"},
                    )
                    return

                self.db.insert_support_reply(
                    feedback_event_id=event_id,
                    channel=channel,
                    sent_to=sent_to,
                    reply_text=reply_text,
                    operator_name=operator_name,
                    status="sent",
                    source="chatwoot",
                    external_message_id=message_id,
                )
                self.db.mark_support_feedback_replied(
                    event_id=event_id,
                    assigned_to=operator_name,
                )
                self._json_response(
                    status=200,
                    payload={
                        "ok": True,
                        "event_id": event_id,
                        "channel": channel,
                        "sent_to": sent_to,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                self.db.insert_support_reply(
                    feedback_event_id=event_id,
                    channel=channel,
                    sent_to=sent_to,
                    reply_text=reply_text,
                    operator_name=operator_name,
                    status="failed",
                    source="chatwoot",
                    external_message_id=message_id,
                    error_message=str(exc),
                )
                self._json_response(
                    status=500,
                    payload={"ok": False, "error": f"reply_failed: {exc}"},
                )
            return

        if request_path == "/support/reply":
            if not self._is_support_authorized():
                self._json_response(
                    status=401,
                    payload={"ok": False, "error": "unauthorized"},
                )
                return
            try:
                body = self._read_json_body()
            except Exception as exc:  # noqa: BLE001
                self._json_response(
                    status=400,
                    payload={"ok": False, "error": f"invalid_json: {exc}"},
                )
                return

            try:
                event_id = int(body.get("event_id"))
            except Exception:  # noqa: BLE001
                self._json_response(
                    status=400,
                    payload={"ok": False, "error": "event_id_required"},
                )
                return

            channel = str(body.get("channel", "")).strip().lower()
            reply_text = str(body.get("reply_text", "")).strip()
            operator_name = str(body.get("operator", "")).strip()
            if channel not in {"telegram", "email"}:
                self._json_response(
                    status=400,
                    payload={"ok": False, "error": "channel_must_be_telegram_or_email"},
                )
                return
            if not reply_text:
                self._json_response(
                    status=400,
                    payload={"ok": False, "error": "reply_text_required"},
                )
                return

            event = self.db.get_support_feedback_event(event_id=event_id)
            if not event:
                self._json_response(
                    status=404,
                    payload={"ok": False, "error": "event_not_found"},
                )
                return

            sent_to = ""
            try:
                if channel == "telegram":
                    chat_id = int(event["telegram_user_id"])
                    _send_telegram_message(
                        token=self.token,
                        chat_id=chat_id,
                        text=_support_reply_telegram_text(
                            event_id=event_id,
                            answer=reply_text,
                        ),
                        raise_on_error=True,
                    )
                    sent_to = str(chat_id)
                else:
                    to_email = str(event.get("reply_email", "")).strip()
                    if not to_email:
                        self._json_response(
                            status=400,
                            payload={"ok": False, "error": "reply_email_missing_for_event"},
                        )
                        return
                    sender = SendGridEmailSender()
                    sender.send_support_reply(
                        to_email=to_email,
                        subject="Vacancy Mirror Support Reply",
                        text=reply_text,
                    )
                    sent_to = to_email

                self.db.insert_support_reply(
                    feedback_event_id=event_id,
                    channel=channel,
                    sent_to=sent_to,
                    reply_text=reply_text,
                    operator_name=operator_name,
                    status="sent",
                    source="support_api",
                )
                self.db.mark_support_feedback_replied(
                    event_id=event_id,
                    assigned_to=operator_name,
                )
                self._json_response(
                    status=200,
                    payload={
                        "ok": True,
                        "event_id": event_id,
                        "channel": channel,
                        "sent_to": sent_to,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                self.db.insert_support_reply(
                    feedback_event_id=event_id,
                    channel=channel,
                    sent_to=sent_to,
                    reply_text=reply_text,
                    operator_name=operator_name,
                    status="failed",
                    source="support_api",
                    error_message=str(exc),
                )
                self._json_response(
                    status=500,
                    payload={"ok": False, "error": f"reply_failed: {exc}"},
                )
            return

        if request_path == "/support/status":
            if not self._is_support_authorized():
                self._json_response(
                    status=401,
                    payload={"ok": False, "error": "unauthorized"},
                )
                return
            try:
                body = self._read_json_body()
                event_id = int(body.get("event_id"))
                status = str(body.get("status", "")).strip().lower()
                operator_name = str(body.get("operator", "")).strip()
            except Exception as exc:  # noqa: BLE001
                self._json_response(
                    status=400,
                    payload={"ok": False, "error": f"invalid_request: {exc}"},
                )
                return

            if status not in {"new", "in_progress", "replied", "closed"}:
                self._json_response(
                    status=400,
                    payload={"ok": False, "error": "invalid_status"},
                )
                return

            updated = self.db.upsert_support_feedback_status(
                event_id=event_id,
                status=status,
                assigned_to=operator_name,
            )
            if not updated:
                self._json_response(
                    status=404,
                    payload={"ok": False, "error": "event_not_found"},
                )
                return
            self._json_response(
                status=200,
                payload={"ok": True, "event_id": event_id, "status": status},
            )
            return

        if request_path != "/webhook":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        sig = self.headers.get("Stripe-Signature", "")

        if self.secret and not _verify_stripe_signature(
            body, sig, self.secret
        ):
            log.warning("Invalid Stripe signature — rejected.")
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid signature")
            return

        try:
            event: dict[str, Any] = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        event_type: str = event.get("type", "")
        data_obj: dict[str, Any] = (
            event.get("data", {}).get("object", {})
        )

        log.info("Stripe event received: %s", event_type)

        if event_type == "checkout.session.completed":
            self._handle_checkout_completed(data_obj)
        elif event_type in (
            "customer.subscription.deleted",
            "customer.subscription.updated",
        ):
            self._handle_subscription_change(
                data_obj, event_type
            )

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def _handle_checkout_completed(
        self, session: dict[str, Any]
    ) -> None:
        """Process a completed Stripe checkout session.

        Reads ``client_reference_id`` (Telegram user ID),
        upserts the subscription in DB, and notifies the user.

        Args:
            session: Stripe checkout.session object.
        """
        ref = session.get("client_reference_id") or ""
        if not ref:
            log.warning(
                "checkout.session.completed has no "
                "client_reference_id — cannot link to user."
            )
            return

        try:
            telegram_user_id = int(ref)
        except ValueError:
            log.error(
                "client_reference_id is not a valid int: %r", ref
            )
            return

        plan = _plan_from_session(session)
        customer_id = session.get("customer") or None
        subscription_id = session.get("subscription") or None

        self.db.upsert_subscription(
            telegram_user_id=telegram_user_id,
            plan=plan,
            stripe_customer_id=customer_id,
            stripe_subscription_id=subscription_id,
            status="active",
        )

        # Sync to Google Sheets.
        try:
            self.sheets.upsert_user(build_user_row(
                telegram_user_id=telegram_user_id,
                plan=plan,
                status="active",
                stripe_customer_id=customer_id or "",
                stripe_subscription_id=subscription_id or "",
            ))
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Sheets sync after checkout failed: %s", exc
            )

        plan_labels = {
            "plus": "⭐ Plus",
            "pro_plus": "🚀 Pro Plus",
        }
        plan_label = plan_labels.get(plan, plan.title())

        _send_telegram_message(
            token=self.token,
            chat_id=telegram_user_id,
            text=(
                f"✅ Payment confirmed!\n\n"
                f"Your {plan_label} subscription is now active.\n"
                f"Thank you for subscribing to Vacancy Mirror 🎉\n\n"
                f"Type /start to return to the main menu."
            ),
        )
        log.info(
            "Subscription activated: user=%s plan=%s",
            telegram_user_id, plan,
        )

    def _handle_subscription_change(
        self,
        subscription: dict[str, Any],
        event_type: str,
    ) -> None:
        """Handle subscription cancellation or update.

        Args:
            subscription: Stripe subscription object.
            event_type: Stripe event type string.
        """
        customer_id = subscription.get("customer")
        status = subscription.get("status", "")
        sub_id = subscription.get("id")

        if event_type == "customer.subscription.deleted":
            new_status = "cancelled"
        elif status in ("past_due", "unpaid"):
            new_status = "past_due"
        else:
            return  # no action needed for other updates

        # Resolve telegram_user_id from DB by stripe_customer_id
        try:
            sub = self.db.get_subscription_by_stripe_customer(
                customer_id
            )
            if not sub:
                log.warning(
                    "No subscription found for customer %s",
                    customer_id,
                )
                return
            telegram_user_id = sub["telegram_user_id"]
            self.db.upsert_subscription(
                telegram_user_id=telegram_user_id,
                plan=sub["plan"],
                stripe_customer_id=customer_id,
                stripe_subscription_id=sub_id,
                status=new_status,
            )
            # Sync to Google Sheets.
            try:
                self.sheets.upsert_user(build_user_row(
                    telegram_user_id=telegram_user_id,
                    plan=sub["plan"],
                    status=new_status,
                    stripe_customer_id=customer_id or "",
                    stripe_subscription_id=sub_id or "",
                ))
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "Sheets sync after sub change failed: %s",
                    exc,
                )
            if new_status == "cancelled":
                _send_telegram_message(
                    token=self.token,
                    chat_id=telegram_user_id,
                    text=(
                        "ℹ️ Your Vacancy Mirror subscription "
                        "has been cancelled.\n\n"
                        "You still have access to the Free plan. "
                        "Type /start to see your options."
                    ),
                )
        except Exception as exc:
            log.exception(
                "Error handling subscription change: %s", exc
            )


class StripeWebhookService:
    """Runs a simple HTTP server to receive Stripe webhook events.

    Attributes:
        port: TCP port to listen on.
        token: Telegram bot token.
        secret: Stripe webhook signing secret.
        db: PostgreSQL service instance.
        sheets: Google Sheets sync service instance.
    """

    def __init__(
        self,
        db_url: str | None = None,
        token: str | None = None,
        secret: str | None = None,
        port: int | None = None,
    ) -> None:
        """Initialise the webhook service.

        Args:
            db_url: PostgreSQL URL. Falls back to DB_URL env var.
            token: Bot token. Falls back to TELEGRAM_BOT_TOKEN.
            secret: Stripe signing secret. Falls back to
                STRIPE_WEBHOOK_SECRET env var.
            port: Port number. Falls back to WEBHOOK_PORT env var,
                then 8080.
        """
        self.db = PostgresJobExportService(db_url=db_url)
        self.sheets = GoogleSheetsService()
        self.token: str = token or os.environ.get(
            "TELEGRAM_BOT_TOKEN", ""
        )
        self.secret: str = secret or os.environ.get(
            "STRIPE_WEBHOOK_SECRET", ""
        )
        self.port: int = port or int(
            os.environ.get("WEBHOOK_PORT", "8080")
        )
        self.stripe_plus_url: str = os.environ.get(
            "STRIPE_PLUS_URL", ""
        )
        self.stripe_pro_plus_url: str = os.environ.get(
            "STRIPE_PRO_PLUS_URL", ""
        )
        self.support_api_token: str = os.environ.get(
            "SUPPORT_API_TOKEN", ""
        )
        self.chatwoot_webhook_token: str = os.environ.get(
            "CHATWOOT_WEBHOOK_TOKEN", ""
        )

        if not self.secret:
            log.warning(
                "STRIPE_WEBHOOK_SECRET not set — "
                "webhook signature verification is DISABLED."
            )

    def run(self) -> None:
        """Start the webhook HTTP server (blocking)."""
        # Inject dependencies into the handler class
        handler = type(
            "_Handler",
            (_WebhookHandler,),
            {
                "db": self.db,
                "token": self.token,
                "secret": self.secret,
                "sheets": self.sheets,
                "stripe_plus_url": self.stripe_plus_url,
                "stripe_pro_plus_url": self.stripe_pro_plus_url,
                "support_api_token": self.support_api_token,
                "chatwoot_webhook_token": self.chatwoot_webhook_token,
            },
        )
        server = http.server.HTTPServer(
            ("0.0.0.0", self.port), handler
        )
        log.info(
            "Stripe webhook server listening on port %d",
            self.port,
        )
        server.serve_forever()

    def run_in_thread(self) -> threading.Thread:
        """Start the webhook server in a background thread.

        Returns:
            The started daemon thread.
        """
        t = threading.Thread(target=self.run, daemon=True)
        t.start()
        return t
