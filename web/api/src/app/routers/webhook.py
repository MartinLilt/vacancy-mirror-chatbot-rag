"""Stripe webhook router."""

from __future__ import annotations

import logging
import os

import stripe
from fastapi import APIRouter, Header, HTTPException, Request

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
) -> dict[str, str]:
    """Handle incoming Stripe webhook events."""
    secret = os.environ["STRIPE_WEBHOOK_SECRET"]
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, secret
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type: str = event["type"]
    log.info("Stripe event received: %s", event_type)

    # TODO: handle customer.subscription.* events
    # (move logic from backend/services/stripe_webhook.py here)

    return {"status": "received"}
