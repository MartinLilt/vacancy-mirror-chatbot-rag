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
from typing import Any

from backend.services.google_sheets import (
    GoogleSheetsService,
    build_user_row,
)
from backend.services.postgres import PostgresJobExportService

log = logging.getLogger(__name__)

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


class _WebhookHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for Stripe webhook events."""

    db: PostgresJobExportService
    sheets: GoogleSheetsService
    token: str
    secret: str
    stripe_plus_url: str
    stripe_pro_plus_url: str

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
        import urllib.parse as _up
        parsed = _up.urlparse(self.path)
        params = dict(_up.parse_qsl(parsed.query))
        uid = params.get("uid", "")

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
        if self.path != "/webhook":
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
