"""Telegram bot service for the Vacancy Mirror assistant.

Provides a conversational interface over the RAG pipeline.
Users can search for job clusters, ask questions about vacancies,
and receive AI-generated summaries — all inside Telegram.

Environment variables
---------------------
TELEGRAM_BOT_TOKEN : str
    Bot token from @BotFather.
ALLOWED_USER_IDS : str, optional
    Comma-separated Telegram user IDs allowed to use the bot.
    If empty, the bot is open to everyone.
OPENAI_API_KEY : str
    OpenAI API key for the assistant.
OPENAI_MODEL : str
    OpenAI model name (default: gpt-4.1-mini).
DB_URL : str
    PostgreSQL connection URL.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from backend.services.google_sheets import (
    GoogleSheetsService,
    build_user_row,
)
from backend.services.chatwoot_client import ChatwootSupportClient
from backend.services.openai import OpenAIMarketAssistantService
from backend.services.postgres import PostgresJobExportService
from backend.services.reasoning_orchestrator import ReasoningOrchestrator

log = logging.getLogger(__name__)

# -- Conversation states --------------------------------------------------
WAITING_QUERY = 0
TRIAL_WAITING_QUERY = 1

# Support conversation states
SUP_WAITING_MESSAGE = 10
SUP_WAITING_REPLY_CHOICE = 11
SUP_WAITING_EMAIL = 12

TRIAL_FOOTER = "\n\n—\nFree trial limit: 35 requests / 24h"
PLAN_LIMITS_24H: dict[str, int] = {
    "free": 35,
    "plus": 60,
    "pro_plus": 120,
}
TRIAL_HISTORY_KEY = "trial_chat_history"
TRIAL_HISTORY_MAX_MESSAGES = 8

# -- Callback data constants ---------------------------------------------
CB_CHAT = "cb_chat"
CB_BENEFITS = "cb_benefits"
CB_PRICING = "cb_pricing"
CB_SUPPORT = "cb_support"
CB_PRIVACY = "cb_privacy"
CB_CANCEL_SUB = "cb_cancel_sub_ask"
CB_CANCEL_SUB_CONFIRM = "cb_cancel_sub_yes"
CB_CANCEL_SUB_ABORT = "cb_cancel_sub_no"

# Support reply-preference callbacks
CB_SUP_REPLY_TG = "sup_reply_tg"
CB_SUP_REPLY_EMAIL = "sup_reply_email"
CB_SUP_NO_REPLY = "sup_no_reply"


def _get_allowed_ids() -> set[int]:
    """Parse ALLOWED_USER_IDS env var into a set of ints."""
    raw = os.environ.get("ALLOWED_USER_IDS", "").strip()
    if not raw:
        return set()
    return {int(x.strip()) for x in raw.split(",") if x.strip()}


def _is_allowed(user_id: int, allowed: set[int]) -> bool:
    """Return True when the user is permitted to use the bot."""
    return not allowed or user_id in allowed


def _env_flag(name: str, default: str = "1") -> bool:
    """Parse bool-like env flags such as 1/0, true/false, yes/no."""
    raw = os.environ.get(name, default).strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _get_trial_history(context: ContextTypes.DEFAULT_TYPE) -> list[dict[str, str]]:
    """Return mutable trial history list from per-user context."""
    history = context.user_data.get(TRIAL_HISTORY_KEY)
    if not isinstance(history, list):
        history = []
        context.user_data[TRIAL_HISTORY_KEY] = history
    return history


def _append_trial_history(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    role: str,
    content: str,
) -> None:
    """Append one message to trial history with bounded size."""
    text = content.strip()
    if not text:
        return
    history = _get_trial_history(context)
    history.append({"role": role, "content": text})
    if len(history) > TRIAL_HISTORY_MAX_MESSAGES:
        del history[:-TRIAL_HISTORY_MAX_MESSAGES]


def _normalize_telegram_text(text: str) -> str:
    """Convert model output into predictable plain text for Telegram."""
    value = text.strip()
    if not value:
        return value

    # Normalize line breaks and common unsupported tags.
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"</p\s*>", "\n\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<p[^>]*>", "", value, flags=re.IGNORECASE)
    value = re.sub(r"<li[^>]*>\s*", "• ", value, flags=re.IGNORECASE)
    value = re.sub(r"</li\s*>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"</?(ul|ol)[^>]*>", "", value, flags=re.IGNORECASE)

    # Convert common plain-text pseudo-lists to visible bullet lines.
    value = re.sub(r"(?m)^\s{2,}(?![•\-*])(\S.+)$", r"• \1", value)
    value = re.sub(r"(?m)^\s*[-*]\s+", "• ", value)

    # Strip any remaining HTML/XML tags to guarantee plain-text output.
    value = re.sub(r"</?[a-z0-9]+[^>]*>", "", value, flags=re.IGNORECASE)

    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _escape_markdown_v2(text: str) -> str:
    """Escape dynamic values for Telegram MarkdownV2 messages."""
    return re.sub(r"([_\*\[\]\(\)~`>#+\-=|{}\.!])", r"\\\1", text)


def _to_base36(n: int) -> str:
    """Convert a non-negative integer to a base-36 string (digits 0-9, letters A-Z)."""
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
    """
    return f"VM-{_to_base36(event_id).zfill(6)}"


# -- Keyboards -----------------------------------------------------------

def _start_keyboard() -> InlineKeyboardMarkup:
    """Build the main menu inline keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "💬 Chat with AI assistant  (trial)",
            callback_data=CB_CHAT,
        )],
        [InlineKeyboardButton(
            "✨ What can this bot do?         ",
            url="https://www.vacancy-mirror.com/benefits",
        )],
        [InlineKeyboardButton(
            "💳 Pricing & subscription plans",
            url="https://www.vacancy-mirror.com/pricing",
        )],
        [InlineKeyboardButton(
            "🆘 Contact support                    ",
            callback_data=CB_SUPPORT,
        )],
        [InlineKeyboardButton(
            "🔒 Privacy policy & terms        ",
            url="https://www.vacancy-mirror.com/privacy",
        )],
    ])


# -- Handlers ------------------------------------------------------------

async def cmd_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle /start — greet user, restore subscription status."""
    allowed: set[int] = context.bot_data["allowed_ids"]
    user = update.effective_user
    if not _is_allowed(user.id, allowed):
        await update.message.reply_text(
            "⛔ You are not authorised to use this bot."
        )
        return

    # Check existing subscription in DB so returning users
    # who deleted the chat history still see their plan.
    db_service: PostgresJobExportService = (
        context.bot_data["db"]
    )
    sub: dict | None = None
    try:
        sub = db_service.get_subscription(user.id)
    except Exception:
        pass  # DB unavailable — treat as no subscription

    # Persist Telegram profile data.
    try:
        db_service.upsert_bot_user(
            telegram_user_id=user.id,
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            username=user.username or "",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to upsert bot user in DB: %s", exc)

    # Always sync current /start activity to Google Sheets.
    sheet_payload = build_user_row(
        telegram_user_id=user.id,
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        username=user.username or "",
        plan=sub["plan"] if sub else "free",
        status=sub["status"] if sub else "none",
        stripe_customer_id=(
            sub.get("stripe_customer_id", "")
            if sub else ""
        ),
        stripe_subscription_id=(
            sub.get("stripe_subscription_id", "")
            if sub else ""
        ),
    )
    try:
        sheet_row = db_service.get_user_for_sheet(user.id)
        if sheet_row:
            sheet_payload = build_user_row(
                telegram_user_id=user.id,
                first_name=str(sheet_row.get("first_name", "")) or (user.first_name or ""),
                last_name=str(sheet_row.get("last_name", "")) or (user.last_name or ""),
                username=str(sheet_row.get("username", "")) or (user.username or ""),
                plan=str(sheet_row.get("plan", "")) or (sub["plan"] if sub else "free"),
                status=str(sheet_row.get("status", "")) or (sub["status"] if sub else "none"),
                stripe_customer_id=str(
                    sheet_row.get("stripe_customer_id", "")
                ) or (
                    sub.get("stripe_customer_id", "")
                    if sub else ""
                ),
                stripe_subscription_id=str(
                    sheet_row.get("stripe_subscription_id", "")
                ) or (
                    sub.get("stripe_subscription_id", "")
                    if sub else ""
                ),
                # Keep historical first_seen, but refresh last_updated on every /start.
                first_seen=str(sheet_row.get("first_seen", "")),
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to load user row for Sheets sync: %s", exc)

    try:
        gs: GoogleSheetsService = context.bot_data["sheets"]
        synced = gs.upsert_user(sheet_payload)
        if not synced:
            log.warning(
                "Sheets sync not applied for /start user_id=%s",
                user.id,
            )
        else:
            log.info(
                "Sheets sync applied for /start user_id=%s",
                user.id,
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to sync user to Sheets: %s", exc)

    if sub and sub.get("status") == "active":
        plan_label: str = (
            "⭐ Plus"
            if sub["plan"] == "plus"
            else "🚀 Pro Plus"
        )
        text = (
            f"👋 *Welcome back, {user.first_name}\\!*\n\n"
            f"✅ Your *{plan_label}* subscription is active\\.\n"
            "All your features are ready to use\\.\n\n"
            "Pick an option below 👇"
        )
    else:
        text = (
            f"👋 *Welcome, {user.first_name}\\!*\n\n"

            "🪞 *Meet Vacancy Mirror*\n"
            "AI\\-powered freelance market intelligence\\.\n"
            "Stop guessing — start knowing\\. 🎯\n\n"

            "✅ *What you get:*\n"
            "🔍 Semantic job search — by meaning, not just "
            "keywords\n"
            "🧩 Role clusters — see who's actually hiring\n"
            "🤖 AI answers on skills, roles & market trends\n"
            "📈 Know what the market wants before you apply\n\n"

            "📡 *Data sources:* publicly available freelance market data\n"
            "including Google Trends signals for trend analytics\\.\n\n"
            "🧠 We continuously collect and analyse market signals to "
            "produce aggregated freelance trends and insights\\.\n\n"

            "🚀 Ready to explore the market?\n"
            "Pick an option below 👇"
        )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_start_keyboard(),
    )


async def cmd_help(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle /help."""
    await cmd_start(update, context)


async def cb_chat(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Handle 'Chat with assistant' button and enter trial chat mode."""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "💬 *Trial chat*\n\n"
        "Ask me anything about the job market ✍️\n\n"
        "_e\\.g\\. \"What skills do React devs need?\"_\n\n"
        "_tap /cancel to exit_"
        f"{TRIAL_FOOTER}",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    return TRIAL_WAITING_QUERY


async def trial_receive_query(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Answer trial chat message with limit checks and LLM response."""
    allowed: set[int] = context.bot_data["allowed_ids"]
    user = update.effective_user
    if not _is_allowed(user.id, allowed):
        return ConversationHandler.END

    prompt = (update.message.text or "").strip()
    if not prompt:
        await update.message.reply_text(
            "⚠️ Please send a non-empty message."
        )
        return TRIAL_WAITING_QUERY

    db: PostgresJobExportService = context.bot_data["db"]
    assistant: OpenAIMarketAssistantService = context.bot_data[
        "assistant_llm"
    ]
    orchestrator: ReasoningOrchestrator | None = context.bot_data.get(
        "assistant_orchestrator"
    )

    plan = "free"
    limit = PLAN_LIMITS_24H["free"]
    try:
        sub = db.get_subscription(user.id)
        if sub and sub.get("status") == "active":
            plan = str(sub.get("plan", "free"))
            limit = PLAN_LIMITS_24H.get(plan, PLAN_LIMITS_24H["free"])
    except Exception:  # noqa: BLE001
        pass

    used = db.count_bot_chat_requests_last_24h(user.id)
    if used >= limit:
        await update.message.reply_text(
            (
                f"⛔ You reached your current limit: {limit} "
                "requests in 24h.\n"
                "Please try again later or upgrade your plan."
                f"{TRIAL_FOOTER}"
            )
        )
        return TRIAL_WAITING_QUERY

    thinking = await update.message.reply_text(
        "🤖 Assistant is thinking..."
    )

    async def _set_status(text: str) -> None:
        try:
            await thinking.edit_text(text)
        except Exception:  # noqa: BLE001
            # Status updates are optional UX; ignore transient edit failures.
            pass

    try:
        history = _get_trial_history(context)
        if orchestrator is not None:
            loop = asyncio.get_running_loop()
            stage_map = {
                "layer1_start": "🧠 Step 1/3: Understanding your request...",
                "layer2_start": "🧭 Step 2/3: Building response plan...",
                "layer3_start": "✍️ Step 3/3: Finalizing answer...",
            }

            def _on_stage(stage: str) -> None:
                text = stage_map.get(stage)
                if not text:
                    return
                asyncio.run_coroutine_threadsafe(
                    _set_status(text),
                    loop,
                )

            result = await asyncio.to_thread(
                orchestrator.run,
                question=prompt,
                history=history,
                stage_callback=_on_stage,
            )
            answer = result.final_answer
        else:
            await _set_status("🔎 Looking for relevant context...")
            answer = assistant.answer_market_question(question=prompt)
    except Exception as exc:  # noqa: BLE001
        log.exception("Trial chat failed: %s", exc)
        try:
            answer = assistant.answer_market_question(question=prompt)
        except Exception as fallback_exc:  # noqa: BLE001
            log.exception("Trial chat fallback failed: %s", fallback_exc)
            await thinking.edit_text(
                "⚠️ Sorry, something went wrong while generating the answer."
                " Please try again."
            )
            return TRIAL_WAITING_QUERY

    _append_trial_history(context, role="user", content=prompt)
    _append_trial_history(context, role="assistant", content=answer)
    rendered_answer = _normalize_telegram_text(answer)

    try:
        db.insert_bot_chat_request(
            telegram_user_id=user.id,
            plan=plan,
        )
        used += 1
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to log trial chat usage: %s", exc)

    await thinking.edit_text(
        f"{rendered_answer}\n\n—\nUsed {used}/{limit}"
    )
    return TRIAL_WAITING_QUERY


async def cb_benefits(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle 'What can this bot do?' button."""
    query = update.callback_query
    await query.answer()

    sections: list[str] = [
        "✨ *What Vacancy Mirror Can Do*",
        (
            "1\\. 📊 *Weekly Freelance Trends Report* `Free`\n\n"
            "Once a week, Vacancy Mirror sends you a summary of how "
            "the freelance market changed over the last 7 days\\.\n\n"
            "You will see:\n"
            "▸ Which roles and skills are growing or declining\n"
            "▸ What clients are searching for most often\n"
            "▸ Which technologies and niches are becoming more popular\n"
            "▸ How demand changed across Upwork categories\n\n"
            "_This report is based only on publicly available "
            "market data\\._"
        ),
        (
            "2\\. 💬 *AI Market Assistant* `Free`\n\n"
            "Chat with an AI assistant about the freelance market\\.\n\n"
            "The assistant can help you:\n"
            "▸ Choose the right direction across all 12 Upwork "
            "categories\n"
            "▸ Understand which skills are worth learning\n"
            "▸ Compare roles, niches, and technologies\n"
            "▸ Build a career roadmap from beginner to Top Rated Plus\n"
            "▸ Improve your proposals, profile structure, and "
            "positioning\n\n"
            "_The assistant provides guidance and recommendations "
            "only\\. It does not access your Upwork account or take "
            "any actions for you\\._\n\n"
            "Limit: 35 messages every 24 hours \\(Free\\), "
            "60 \\(Plus\\), 120 \\(Pro Plus\\)\\."
        ),
        (
            "3\\. 📈 *Weekly Trend Charts* `Free`\n\n"
            "Receive simple charts every week that compare the current "
            "week with the previous one\\.\n\n"
            "You can quickly understand:\n"
            "▸ Which niches are growing or shrinking\n"
            "▸ Which skills are becoming more or less popular\n"
            "▸ How the freelance market is changing over time\n\n"
            "_Charts are created from publicly available job market "
            "information\\._"
        ),
        (
            "4\\. 🎯 *Profile Optimisation Expert* `Plus`\n\n"
            "Get recommendations on how to improve your freelancer "
            "profile using current market trends\\.\n\n"
            "The system analyses public market demand and suggests:\n"
            "▸ Better profile titles\n"
            "▸ More effective descriptions\n"
            "▸ Important keywords and skills to include\n"
            "▸ Better positioning for your chosen niche\n\n"
            "_Vacancy Mirror does not edit or access your profile "
            "automatically\\. All recommendations are for you to "
            "review and apply manually\\._"
        ),
        (
            "5\\. 🤖 *Weekly Profile & Projects Agent* `Plus`\n\n"
            "Once a week, you receive a personalised report showing "
            "how to update your freelancer profile and up to 5 "
            "portfolio projects\\.\n\n"
            "The report is based on:\n"
            "▸ Your previous preferences and saved information inside "
            "Vacancy Mirror\n"
            "▸ Current public market trends\n"
            "▸ Changes in demand since the previous week\n\n"
            "_The service does not connect to or modify your Upwork "
            "account\\._"
        ),
        (
            "6\\. 🚀 *Extended Projects Agent* `Pro Plus`\n\n"
            "Includes everything from the previous plan, but allows "
            "recommendations for up to 12 portfolio projects instead "
            "of 5\\.\n\n"
            "This gives you full coverage of your portfolio and helps "
            "you keep all of your projects aligned with current market "
            "demand\\."
        ),
        (
            "7\\. 🏷️ *Weekly Skills & Tags Report* `Pro Plus`\n\n"
            "Every week, you receive a report showing which keywords, "
            "tags, and skill combinations appear most often in public "
            "freelance job listings\\.\n\n"
            "You can use this information to improve:\n"
            "▸ Your profile\n"
            "▸ Your proposals\n"
            "▸ Your portfolio descriptions\n"
            "▸ Your positioning in the market\n\n"
            "_Vacancy Mirror provides recommendations only and does "
            "not automatically send proposals, update profiles, or "
            "interact with third\\-party platforms\\._"
        ),
    ]

    for section in sections:
        await query.message.reply_text(
            section,
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    await query.message.reply_text(
        "_That's everything Vacancy Mirror can do for you\\._",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_start_keyboard(),
    )


async def cb_pricing(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle 'Pricing' button — send three plans as a message burst.

    Buttons are personalised based on the user's current plan:
    - free  → "Subscribe to Plus" + "Subscribe to Pro Plus"
    - plus  → current plan badge on Plus + "Upgrade to Pro Plus"
    - pro_plus → current plan badge on Pro Plus, no upgrade button
    """
    query = update.callback_query
    await query.answer()

    user_id: int = update.effective_user.id
    db: PostgresJobExportService = context.bot_data["db"]

    # Detect current plan / status.
    current_plan: str = "free"
    is_active: bool = False
    try:
        sub = db.get_subscription(user_id)
        if sub and sub.get("status") == "active":
            current_plan = sub.get("plan", "free")
            is_active = True
    except Exception:  # noqa: BLE001
        pass

    # Build pay redirect URLs through our own server so that
    # Telegram shows a clean domain instead of a long Stripe URL
    # with client_reference_id query param.
    _base: str = os.environ.get("WEBHOOK_BASE_URL", "")
    _stripe_plus_base: str = os.environ.get(
        "STRIPE_PLUS_URL", "https://buy.stripe.com/plus"
    )
    _stripe_pro_plus_base: str = os.environ.get(
        "STRIPE_PRO_PLUS_URL", "https://buy.stripe.com/pro_plus"
    )
    if _base:
        stripe_plus_url: str = (
            f"{_base}/pay/plus?uid={user_id}"
        )
        stripe_pro_plus_url: str = (
            f"{_base}/pay/pro-plus?uid={user_id}"
        )
    else:
        stripe_plus_url = (
            f"{_stripe_plus_base}"
            f"?client_reference_id={user_id}"
        )
        stripe_pro_plus_url = (
            f"{_stripe_pro_plus_base}"
            f"?client_reference_id={user_id}"
        )

    # Header
    await query.message.reply_text(
        "💳 *Pricing & Subscription Plans*\n\n"
        "_All plans are billed monthly\\. "
        "Annual billing is not available\\._",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    # Free plan — show "✅ Your current plan" badge when active.
    free_badge = (
        "\n\n✅ _This is your current plan\\._"
        if (not is_active)
        else ""
    )
    await query.message.reply_text(
        "🆓 *Free Plan*\n\n"
        "Everything you need to get started\\.\n\n"
        "Includes:\n"
        "▸ 📊 Weekly Freelance Trends Report\n"
        "▸ 💬 AI Market Assistant "
        "\\(limit: 35 messages every 24 hours\\)\n"
        "▸ 📈 Weekly Trend Charts\n\n"
        "_No payment required\\. Available to all users\\._"
        f"{free_badge}",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    # Plus plan — button depends on current plan.
    if is_active and current_plan == "plus":
        plus_button: list[list[InlineKeyboardButton]] = []
        plus_badge = "\n\n✅ _This is your current plan\\._"
    elif is_active and current_plan == "pro_plus":
        # Already on higher plan — no plus button.
        plus_button = []
        plus_badge = ""
    else:
        plus_button = [[InlineKeyboardButton(
            "⭐ Subscribe to Plus",
            url=stripe_plus_url,
        )]]
        plus_badge = ""

    await query.message.reply_text(
        "⭐ *Plus Plan* — \\$9\\.99 / month\n\n"
        "Everything in Free, plus advanced profile tools\\.\n\n"
        "Includes:\n"
        "▸ 💬 AI Market Assistant "
        "\\(limit: 60 messages every 24 hours\\)\n"
        "▸ 🎯 Profile Optimisation Expert\n"
        "▸ 🤖 Weekly Profile & Projects Agent\n"
        "   \\(up to 5 portfolio projects\\)\n\n"
        "_Vacancy Mirror does not access or modify your "
        "profile automatically\\. All recommendations are "
        "for you to apply manually\\._"
        f"{plus_badge}",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=(
            InlineKeyboardMarkup(plus_button)
            if plus_button else None
        ),
    )

    # Pro Plus plan — show upgrade button for Plus users.
    if is_active and current_plan == "pro_plus":
        pro_button: list[list[InlineKeyboardButton]] = []
        pro_badge = "\n\n✅ _This is your current plan\\._"
    elif is_active and current_plan == "plus":
        pro_button = [[InlineKeyboardButton(
            "🚀 Upgrade to Pro Plus",
            url=stripe_pro_plus_url,
        )]]
        pro_badge = (
            "\n\n💡 _Upgrading from Plus — you will only be "
            "charged the prorated difference for the rest of "
            "the current billing period\\._"
        )
    else:
        pro_button = [[InlineKeyboardButton(
            "🚀 Subscribe to Pro Plus",
            url=stripe_pro_plus_url,
        )]]
        pro_badge = ""

    await query.message.reply_text(
        "🚀 *Pro Plus Plan* — \\$19\\.99 / month\n\n"
        "Everything in Plus, with maximum coverage\\.\n\n"
        "Includes:\n"
        "▸ 💬 AI Market Assistant "
        "\\(limit: 120 messages every 24 hours\\)\n"
        "▸ 🚀 Extended Projects Agent\n"
        "   \\(up to 12 portfolio projects\\)\n"
        "▸ 🏷️ Weekly Skills & Tags Report\n\n"
        "_Full portfolio coverage aligned with market "
        "trends every week\\._"
        f"{pro_badge}",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=(
            InlineKeyboardMarkup(pro_button)
            if pro_button else None
        ),
    )

    # Footer: support + optional cancel button
    footer_buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(
            "❓ Questions? Contact support",
            callback_data=CB_SUPPORT,
        )],
        *_cancel_sub_button(context.bot_data["db"], user_id),
    ]
    await query.message.reply_text(
        "💬 Need help or want to manage your subscription?",
        reply_markup=InlineKeyboardMarkup(footer_buttons),
    )


def _cancel_sub_button(
    db: PostgresJobExportService,
    user_id: int,
) -> list[list[InlineKeyboardButton]]:
    """Return a cancel-subscription button row if user has one.

    Returns an empty list when no active subscription is found,
    so the caller can safely unpack it with ``*``.
    """
    try:
        sub = db.get_subscription(user_id)
    except Exception:
        return []
    if sub and sub.get("status") == "active":
        return [[InlineKeyboardButton(
            "❌ Cancel my subscription",
            callback_data=CB_CANCEL_SUB,
        )]]
    return []


async def cb_cancel_sub(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Ask the user to confirm subscription cancellation."""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "⚠️ *Cancel your subscription?*\n\n"
        "Your plan will remain active until the end of the "
        "current billing period\\. After that you will be "
        "moved to the Free plan\\.\n\n"
        "Are you sure you want to cancel?",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "✅ Yes, cancel my subscription",
                callback_data=CB_CANCEL_SUB_CONFIRM,
            )],
            [InlineKeyboardButton(
                "↩️ No, keep my subscription",
                callback_data=CB_CANCEL_SUB_ABORT,
            )],
        ]),
    )


def _fetch_stripe_period_end(sub_id: str) -> str | None:
    """Fetch current_period_end from Stripe and return formatted date.

    Parameters
    ----------
    sub_id:
        Stripe subscription ID (e.g. ``sub_xxx``).

    Returns
    -------
    str | None
        Human-readable date such as ``"29 April 2026"``, or ``None``
        when the date cannot be determined.
    """
    if not sub_id:
        return None
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key:
        return None
    token = base64.b64encode(f"{key}:".encode()).decode()
    req = urllib.request.Request(
        f"https://api.stripe.com/v1/subscriptions/{sub_id}",
        headers={"Authorization": f"Basic {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data: dict = json.loads(resp.read())
            ts = data.get("current_period_end")
            if ts:
                dt = datetime.fromtimestamp(
                    int(ts), tz=timezone.utc
                )
                return dt.strftime("%-d %B %Y")
    except urllib.error.URLError as exc:
        log.warning("Stripe API request failed: %s", exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("Unexpected error fetching period end: %s", exc)
    return None


async def cb_cancel_sub_confirm(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Mark subscription as cancelled in DB and notify user."""
    query = update.callback_query
    await query.answer()
    user_id: int = update.effective_user.id
    db: PostgresJobExportService = context.bot_data["db"]

    end_date: str | None = None
    sub: dict | None = None
    try:
        sub = db.get_subscription(user_id)
        if sub:
            end_date = _fetch_stripe_period_end(
                sub.get("stripe_subscription_id", "")
            )
            db.upsert_subscription(
                telegram_user_id=user_id,
                plan=sub["plan"],
                stripe_customer_id=sub.get(
                    "stripe_customer_id"
                ),
                stripe_subscription_id=sub.get(
                    "stripe_subscription_id"
                ),
                status="cancelled",
            )
        cancelled = True
    except Exception as exc:  # noqa: BLE001
        log.error("Failed to cancel subscription: %s", exc)
        cancelled = False

    # Sync updated status to Google Sheets.
    if cancelled and sub:
        try:
            tg_user = update.effective_user
            gs: GoogleSheetsService = context.bot_data["sheets"]
            gs.upsert_user(build_user_row(
                telegram_user_id=user_id,
                first_name=tg_user.first_name or "",
                last_name=tg_user.last_name or "",
                username=tg_user.username or "",
                plan=sub["plan"],
                status="cancelled",
                stripe_customer_id=sub.get(
                    "stripe_customer_id", ""
                ),
                stripe_subscription_id=sub.get(
                    "stripe_subscription_id", ""
                ),
            ))
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Sheets sync after cancel failed: %s", exc
            )

    if cancelled:
        if end_date:
            until_text = (
                f"until *{end_date}*"
            )
        else:
            until_text = (
                "until the end of the current billing period"
            )
        await query.message.reply_text(
            f"✅ *Subscription cancelled*\n\n"
            f"Your plan will stay active {until_text}\\. "
            f"After that you will be on the Free plan\\.\n\n"
            "You can re\\-subscribe any time via the "
            "*Pricing* menu\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    else:
        await query.message.reply_text(
            "⚠️ Something went wrong\\. "
            "Please contact support\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )


async def cb_cancel_sub_abort(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """User changed their mind — dismiss the confirmation."""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "👍 No changes made\\. Your subscription is still "
        "active\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


def _support_admin_id() -> int | None:
    """Return the support admin Telegram user ID from env."""
    raw = os.environ.get("SUPPORT_ADMIN_ID", "").strip()
    return int(raw) if raw else None


def _reply_choice_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for choosing how to receive the support reply."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "📩 Reply in Telegram",
            callback_data=CB_SUP_REPLY_TG,
        )],
        [InlineKeyboardButton(
            "📧 Reply by email",
            callback_data=CB_SUP_REPLY_EMAIL,
        )],
        [InlineKeyboardButton(
            "🚫 No reply needed",
            callback_data=CB_SUP_NO_REPLY,
        )],
    ])


def _is_valid_email(value: str) -> bool:
    """Return True for a basic user-provided email address."""
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value.strip()))


def _support_username(user: object) -> str:
    """Normalize Telegram username for storage and display."""
    raw = (getattr(user, "username", "") or "").strip()
    if not raw:
        return ""
    return raw if raw.startswith("@") else f"@{raw}"


async def _pin_support_ticket_message(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
) -> None:
    """Pin original user support message; ignore Telegram pin limitations."""
    if message_id <= 0:
        return
    try:
        await context.bot.pin_chat_message(
            chat_id=chat_id,
            message_id=message_id,
            disable_notification=True,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to pin support ticket message %s: %s", message_id, exc)


async def cb_privacy(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle 'Privacy Policy & Terms' button — send as a message burst."""
    query = update.callback_query
    await query.answer()

    sections: list[str] = [
        (
            "🔒 *Privacy Policy & Terms of Use*\n"
            "_Effective date: March 29, 2026_"
        ),
        (
            "*1\\. About Vacancy Mirror*\n\n"
            "Vacancy Mirror is an independent freelance market intelligence "
            "tool designed to help freelancers understand market demand "
            "through semantic search, trend analysis, clustering, and "
            "AI\\-generated insights\\.\n\n"
            "Vacancy Mirror is not affiliated with, endorsed by, sponsored "
            "by, or officially connected to Upwork Inc\\., Telegram, Google, "
            "or any other third\\-party platform\\.\n\n"
            "All trademarks, logos, and platform names remain the property "
            "of their respective owners\\."
        ),
        (
            "*2\\. Data Sources*\n\n"
            "Vacancy Mirror analyses information that is publicly available "
            "on the internet, including:\n"
            "▸ Public job listings\n"
            "▸ Public search engine results\n"
            "▸ Publicly visible job titles, descriptions, skills, "
            "categories, budgets, and metadata\n\n"
            "We do not require or request: usernames, passwords, cookies, "
            "API keys, session tokens, or browser credentials\\.\n\n"
            "We do not access or process: private accounts, freelancer or "
            "client dashboards, messages, proposals, contracts, payment "
            "information, private attachments, or any non\\-public "
            "information\\.\n\n"
            "If a third\\-party platform changes its access rules, "
            "Vacancy Mirror may modify, limit, or discontinue the affected "
            "functionality at any time\\."
        ),
        (
            "*3\\. Read\\-Only Service*\n\n"
            "Vacancy Mirror is strictly a read\\-only analytical "
            "service\\.\n\n"
            "The service does not:\n"
            "▸ Submit proposals or apply to jobs\n"
            "▸ Contact clients or send messages\n"
            "▸ Post or edit jobs\n"
            "▸ Log into third\\-party platforms on your behalf\n"
            "▸ Automate account activity\n"
            "▸ Take any action using your Upwork or other platform account\n\n"
            "The service is intended only to help you better understand "
            "the freelance market\\."
        ),
        (
            "*4\\. AI\\-Generated Insights*\n\n"
            "Vacancy Mirror uses AI to generate market summaries, trend "
            "reports, skill recommendations, search results, and role "
            "clusters\\.\n\n"
            "AI\\-generated insights may occasionally be incomplete, "
            "inaccurate, delayed, or based on limited data\\.\n\n"
            "Vacancy Mirror does not guarantee: hiring success, more "
            "invitations or contracts, increased income, accuracy or "
            "completeness of all data, or availability of specific jobs "
            "or trends\\.\n\n"
            "You should independently verify important decisions before "
            "relying on the service\\."
        ),
        (
            "*5\\. Your Data*\n\n"
            "To provide the service, we may store:\n"
            "▸ Your Telegram user ID and username\n"
            "▸ Messages you send to the bot\n"
            "▸ Search history and saved preferences\n"
            "▸ Generated reports\n"
            "▸ Technical logs \\(timestamps, language settings\\)\n\n"
            "We use this information only to provide and improve the "
            "service, save your preferences, and prevent abuse\\.\n\n"
            "We do not sell, rent, or share your personal data with "
            "advertisers or unrelated third parties\\."
        ),
        (
            "*6\\. Data Retention*\n\n"
            "We keep your data only as long as reasonably necessary to "
            "provide the service\\.\n\n"
            "Unless required for legal or security reasons:\n"
            "▸ Chat history may be automatically removed after a reasonable "
            "period\n"
            "▸ Technical logs may be deleted automatically\n"
            "▸ Deleted accounts and associated data may be permanently "
            "erased within 30 days\n\n"
            "You may request deletion of your data at any time\\."
        ),
        (
            "*7\\. GDPR & EU Rights*\n\n"
            "If you are located in the EU, EEA, or UK, you have the "
            "right to:\n"
            "▸ Access your data\n"
            "▸ Correct inaccurate data\n"
            "▸ Request deletion of your data\n"
            "▸ Restrict or object to processing\n"
            "▸ Export your data\n"
            "▸ Withdraw consent at any time\n\n"
            "Our legal basis for processing: your consent, providing the "
            "requested service, legitimate interest in operating the "
            "service, and compliance with legal obligations\\.\n\n"
            "If you request deletion, we will remove your personal data "
            "unless legally required to keep it\\."
        ),
        (
            "*8\\. Security*\n\n"
            "We take reasonable technical and organisational measures to "
            "protect your information, including encrypted connections, "
            "restricted access to stored data, internal access controls, "
            "and logging & monitoring\\.\n\n"
            "However, no internet service can be guaranteed to be "
            "completely secure\\. You use the service at your own risk\\."
        ),
        (
            "*9\\. Intellectual Property*\n\n"
            "All job listings, platform names, trademarks, logos, and "
            "third\\-party content remain the property of their respective "
            "owners\\.\n\n"
            "Vacancy Mirror only provides independent analysis and does not "
            "claim ownership of any third\\-party content\\.\n\n"
            "You may not use Vacancy Mirror to copy or redistribute large "
            "amounts of third\\-party content, reproduce job listings in "
            "bulk, misrepresent yourself as Upwork or another platform, or "
            "violate the intellectual property rights of others\\."
        ),
        (
            "*10\\. Prohibited Use*\n\n"
            "You may not use Vacancy Mirror to:\n"
            "▸ Break the law or violate third\\-party platform rules\n"
            "▸ Spam, harass, or abuse others\n"
            "▸ Automate proposals, bidding, or messaging\n"
            "▸ Reverse engineer or abuse the service\n"
            "▸ Resell or copy the service without permission\n\n"
            "We reserve the right to suspend or terminate access in case "
            "of misuse\\."
        ),
        (
            "*11\\. Changes*\n\n"
            "We may update these Terms and Privacy Policy at any time\\.\n\n"
            "The latest version will always be available inside the bot "
            "or on our website\\.\n\n"
            "By continuing to use Vacancy Mirror, you agree to the latest "
            "version\\."
        ),
        (
            "*12\\. Contact*\n\n"
            "For support, privacy requests, or data deletion:\n\n"
            "📧 support@vacancymirror\\.com"
        ),
    ]

    for section in sections:
        await query.message.reply_text(
            section,
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    await query.message.reply_text(
        "_You have received the full Privacy Policy & Terms of Use\\._",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_start_keyboard(),
    )


async def cb_support(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Handle 'Contact support' button — start support conversation."""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "🆘 *Contact Support*\n\n"
        "Please describe your issue or question below\\.\n"
        "Your message will be sent directly to our support team\\.\n\n"
        "_tap /cancel to exit_",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    return SUP_WAITING_MESSAGE


async def sup_receive_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Store the user's support message and ask reply preference."""
    context.user_data["sup_message"] = update.message.text.strip()
    context.user_data["sup_message_id"] = int(update.message.message_id or 0)
    await update.message.reply_text(
        "📬 *Do you need a reply from support?*\n\n"
        "If yes — choose how you'd like to receive it\\.\n\n"
        "_Note: if you request a reply, expect it within "
        "*3 business days*\\._",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=_reply_choice_keyboard(),
    )
    return SUP_WAITING_REPLY_CHOICE


async def sup_reply_tg(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """User wants a Telegram reply — forward to admin and finish."""
    query = update.callback_query
    await query.answer()
    event_id: int | None = None
    message_text = str(context.user_data.get("sup_message", "")).strip()
    support_message_id = int(context.user_data.get("sup_message_id", 0) or 0)
    try:
        db: PostgresJobExportService = context.bot_data["db"]
        event_id = db.insert_support_feedback_event(
            telegram_user_id=update.effective_user.id,
            telegram_username=_support_username(update.effective_user),
            telegram_full_name=update.effective_user.full_name or "",
            reply_channel="telegram",
            feedback_message=message_text,
            telegram_message_id=support_message_id,
        )
        try:
            client = ChatwootSupportClient()
            chatwoot = client.create_support_conversation(
                event_id=event_id,
                telegram_user_id=update.effective_user.id,
                telegram_username=_support_username(update.effective_user),
                telegram_full_name=update.effective_user.full_name or "",
                reply_channel="telegram",
                feedback_message=message_text,
            )
            db.set_support_feedback_chatwoot_link(
                event_id=event_id,
                conversation_id=int(chatwoot.get("conversation_id", 0)),
                contact_id=int(chatwoot.get("contact_id", 0)),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to push support feedback to Chatwoot: %s", exc)
            await _forward_to_admin(
                context=context,
                user=update.effective_user,
                reply_via="Telegram",
                extra=None,
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to persist support feedback (telegram): %s", exc)
        await _forward_to_admin(
            context=context,
            user=update.effective_user,
            reply_via="Telegram",
            extra=None,
        )

    ticket_line = ""
    if event_id is not None and event_id > 0:
        ticket_line = (
            "\n\n"
            f"Ticket ID: `{_support_ticket_public_id(event_id)}`"
        )

    await query.message.reply_text(
        "✅ *Message sent to support\\!*\n\n"
        "We will reply to you here in Telegram\\.\n"
        "Expect a response within *3 business days*\\. ⏳"
        f"{ticket_line}",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    await _pin_support_ticket_message(
        context=context,
        chat_id=update.effective_chat.id,
        message_id=support_message_id,
    )
    context.user_data.pop("sup_message", None)
    context.user_data.pop("sup_message_id", None)
    return ConversationHandler.END


async def sup_reply_email(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """User wants an email reply — ask for their email address."""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "📧 Please enter your email address and we will reply there:",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    return SUP_WAITING_EMAIL


async def sup_receive_email(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Receive email address, forward to admin and finish."""
    email = update.message.text.strip()
    if not _is_valid_email(email):
        await update.message.reply_text(
            "⚠️ Please enter a valid email address \\(example: name@example\\.com\\)\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return SUP_WAITING_EMAIL

    event_id: int | None = None
    message_text = str(context.user_data.get("sup_message", "")).strip()
    support_message_id = int(context.user_data.get("sup_message_id", 0) or 0)
    try:
        db: PostgresJobExportService = context.bot_data["db"]
        event_id = db.insert_support_feedback_event(
            telegram_user_id=update.effective_user.id,
            telegram_username=_support_username(update.effective_user),
            telegram_full_name=update.effective_user.full_name or "",
            reply_channel="email",
            reply_email=email,
            feedback_message=message_text,
            telegram_message_id=support_message_id,
        )
        try:
            client = ChatwootSupportClient()
            chatwoot = client.create_support_conversation(
                event_id=event_id,
                telegram_user_id=update.effective_user.id,
                telegram_username=_support_username(update.effective_user),
                telegram_full_name=update.effective_user.full_name or "",
                reply_channel="email",
                reply_email=email,
                feedback_message=message_text,
            )
            db.set_support_feedback_chatwoot_link(
                event_id=event_id,
                conversation_id=int(chatwoot.get("conversation_id", 0)),
                contact_id=int(chatwoot.get("contact_id", 0)),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to push support feedback to Chatwoot: %s", exc)
            await _forward_to_admin(
                context=context,
                user=update.effective_user,
                reply_via="email",
                extra=email,
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to persist support feedback (email): %s", exc)
        await _forward_to_admin(
            context=context,
            user=update.effective_user,
            reply_via="email",
            extra=email,
        )

    ticket_line = ""
    if event_id is not None and event_id > 0:
        ticket_line = (
            "\n\n"
            f"Ticket ID: `{_support_ticket_public_id(event_id)}`"
        )
    safe_email = _escape_markdown_v2(email)
    await update.message.reply_text(
        "✅ *Message sent to support\\!*\n\n"
        f"We will reply to *{safe_email}*\\.\n"
        "Expect a response within *3 business days*\\. ⏳"
        f"{ticket_line}",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    await _pin_support_ticket_message(
        context=context,
        chat_id=update.effective_chat.id,
        message_id=support_message_id,
    )
    context.user_data.pop("sup_message", None)
    context.user_data.pop("sup_message_id", None)
    return ConversationHandler.END


async def sup_no_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """User does not need a reply — forward to admin and finish."""
    query = update.callback_query
    await query.answer()
    event_id: int | None = None
    message_text = str(context.user_data.get("sup_message", "")).strip()
    support_message_id = int(context.user_data.get("sup_message_id", 0) or 0)
    try:
        db: PostgresJobExportService = context.bot_data["db"]
        event_id = db.insert_support_feedback_event(
            telegram_user_id=update.effective_user.id,
            telegram_username=_support_username(update.effective_user),
            telegram_full_name=update.effective_user.full_name or "",
            reply_channel="none",
            feedback_message=message_text,
            telegram_message_id=support_message_id,
        )
        try:
            client = ChatwootSupportClient()
            chatwoot = client.create_support_conversation(
                event_id=event_id,
                telegram_user_id=update.effective_user.id,
                telegram_username=_support_username(update.effective_user),
                telegram_full_name=update.effective_user.full_name or "",
                reply_channel="none",
                feedback_message=message_text,
            )
            db.set_support_feedback_chatwoot_link(
                event_id=event_id,
                conversation_id=int(chatwoot.get("conversation_id", 0)),
                contact_id=int(chatwoot.get("contact_id", 0)),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to push support feedback to Chatwoot: %s", exc)
            await _forward_to_admin(
                context=context,
                user=update.effective_user,
                reply_via=None,
                extra=None,
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to persist support feedback (no-reply): %s", exc)
        await _forward_to_admin(
            context=context,
            user=update.effective_user,
            reply_via=None,
            extra=None,
        )

    ticket_line = ""
    if event_id is not None and event_id > 0:
        ticket_line = (
            "\n\n"
            f"Ticket ID: `{_support_ticket_public_id(event_id)}`"
        )
    await query.message.reply_text(
        "✅ *Message sent to support\\!*\n\n"
        "Thank you for your feedback\\. 🙏"
        f"{ticket_line}",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    await _pin_support_ticket_message(
        context=context,
        chat_id=update.effective_chat.id,
        message_id=support_message_id,
    )
    context.user_data.pop("sup_message", None)
    context.user_data.pop("sup_message_id", None)
    return ConversationHandler.END


async def _forward_to_admin(
    context: ContextTypes.DEFAULT_TYPE,
    user: object,
    reply_via: str | None,
    extra: str | None,
) -> None:
    """Forward a support message to the admin Telegram account.

    Args:
        context: Handler context providing bot access.
        user: The Telegram user who sent the message.
        reply_via: "Telegram", "email", or None.
        extra: Email address when reply_via is "email".
    """
    admin_id = _support_admin_id()
    if admin_id is None:
        log.warning(
            "SUPPORT_ADMIN_ID not set — support message not forwarded."
        )
        return

    message = context.user_data.get("sup_message", "—")
    username = f"@{user.username}" if user.username else "no username"

    if reply_via == "Telegram":
        reply_info = f"Reply via: Telegram (user id: {user.id})"
    elif reply_via == "email":
        reply_info = f"Reply via: email — {extra}"
    else:
        reply_info = "No reply needed"

    text = (
        f"🆘 New support message\n\n"
        f"From: {user.full_name} ({username})\n"
        f"User ID: {user.id}\n"
        f"{reply_info}\n\n"
        f"Message:\n{message}"
    )
    try:
        await context.bot.send_message(
            chat_id=admin_id,
            text=text,
        )
    except Exception as exc:
        log.exception(
            "Failed to forward support message to admin: %s", exc
        )


async def cmd_stats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle /stats — show raw_jobs count from DB."""
    allowed: set[int] = context.bot_data["allowed_ids"]
    user = update.effective_user
    if not _is_allowed(user.id, allowed):
        return

    db_service: PostgresJobExportService = context.bot_data["db"]
    await update.message.chat.send_action(ChatAction.TYPING)

    try:
        stats = db_service.get_stats()
    except Exception as exc:
        log.exception("Failed to fetch stats: %s", exc)
        await update.message.reply_text(
            "❌ Failed to fetch statistics. Please try again later."
        )
        return

    lines = ["📊 *Database statistics:*\n"]
    for category, count in stats.items():
        lines.append(f"• *{category}*: {count:,} jobs")
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN_V2,
    )


async def cmd_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Handle /search — ask user for a search query."""
    allowed: set[int] = context.bot_data["allowed_ids"]
    if not _is_allowed(update.effective_user.id, allowed):
        return ConversationHandler.END

    await update.message.reply_text(
        "🔍 What job are you looking for?\n"
        "_e\\.g\\. React dev, data analyst, copywriter_",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    return WAITING_QUERY


async def handle_search_query(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Receive the user's search text and return matching jobs."""
    allowed: set[int] = context.bot_data["allowed_ids"]
    if not _is_allowed(update.effective_user.id, allowed):
        return ConversationHandler.END

    query_text = update.message.text.strip()
    if not query_text:
        await update.message.reply_text(
            "⚠️ Please send a non-empty search term."
        )
        return WAITING_QUERY

    await update.message.chat.send_action(ChatAction.TYPING)

    db_service: PostgresJobExportService = context.bot_data["db"]
    try:
        jobs = db_service.search_jobs(query=query_text, limit=5)
    except Exception as exc:
        log.exception(
            "Search failed for query %r: %s", query_text, exc
        )
        await update.message.reply_text(
            "❌ Search failed. Please try again later."
        )
        return ConversationHandler.END

    if not jobs:
        await update.message.reply_text(
            f"😕 No jobs found for *{query_text}*\\.\n"
            "Try different keywords\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"✅ Found *{len(jobs)}* matching jobs for *{query_text}*:",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    for job in jobs:
        title = job.get("title", "No title")
        category = job.get("category_name", "—")
        uid = job.get("uid", "")
        url = (
            f"https://www.upwork.com/jobs/~{uid}" if uid else "—"
        )
        text = (
            f"📌 *{title}*\n"
            f"Category: {category}\n"
            f"[View on Upwork]({url})"
        )
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True,
        )

    return ConversationHandler.END


async def handle_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Cancel the current conversation."""
    context.user_data.pop(TRIAL_HISTORY_KEY, None)
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


async def cmd_restart(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle /restart — clear state and show the main menu again."""
    context.user_data.clear()
    await cmd_start(update, context)


async def handle_unknown(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle unrecognised messages outside a conversation."""
    await update.message.reply_text(
        "🤷 Not sure what you mean.\nTap /help to see options."
    )


# -- Bot builder ---------------------------------------------------------

class TelegramBotService:
    """Manages the Telegram bot lifecycle.

    Attributes:
        token: Bot token from @BotFather.
        allowed_ids: Set of permitted Telegram user IDs (empty = all).
        db: PostgreSQL service instance.
        sheets: Google Sheets sync service instance.
    """

    def __init__(
        self,
        token: str | None = None,
        db_url: str | None = None,
    ) -> None:
        """Initialise the bot service.

        Args:
            token: Telegram bot token. Falls back to TELEGRAM_BOT_TOKEN
                environment variable.
            db_url: PostgreSQL connection URL. Falls back to DB_URL
                environment variable.

        Raises:
            ValueError: If the token is not provided.
        """
        self.token: str = token or os.environ.get(
            "TELEGRAM_BOT_TOKEN", ""
        )
        if not self.token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN is required but not set."
            )
        self.allowed_ids: set[int] = _get_allowed_ids()
        self.db: PostgresJobExportService = PostgresJobExportService(
            db_url=db_url
        )
        self.sheets: GoogleSheetsService = GoogleSheetsService()
        self.assistant_llm = OpenAIMarketAssistantService()
        self.orchestrator_enabled = _env_flag(
            "ASSISTANT_ORCHESTRATOR_ENABLED", default="1"
        )
        self.assistant_orchestrator: ReasoningOrchestrator | None = None
        if self.orchestrator_enabled:
            self.assistant_orchestrator = ReasoningOrchestrator(
                llm=self.assistant_llm,
                max_history_messages=TRIAL_HISTORY_MAX_MESSAGES,
            )

    def _build_application(self) -> Application:
        """Build and configure the telegram Application."""
        app = (
            Application.builder()
            .token(self.token)
            .build()
        )

        # Shared state available to all handlers
        app.bot_data["allowed_ids"] = self.allowed_ids
        app.bot_data["db"] = self.db
        app.bot_data["sheets"] = self.sheets
        app.bot_data["assistant_llm"] = self.assistant_llm
        app.bot_data["assistant_orchestrator"] = self.assistant_orchestrator

        # Trial chat conversation (triggered by inline button)
        trial_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(cb_chat, pattern=CB_CHAT),
            ],
            states={
                TRIAL_WAITING_QUERY: [
                    CallbackQueryHandler(cb_chat, pattern=CB_CHAT),
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        trial_receive_query,
                    ),
                ],
            },
            fallbacks=[
                CommandHandler("cancel", handle_cancel),
            ],
            allow_reentry=True,
        )

        # /search conversation
        search_conv = ConversationHandler(
            entry_points=[
                CommandHandler("search", cmd_search),
            ],
            states={
                WAITING_QUERY: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        handle_search_query,
                    ),
                ],
            },
            fallbacks=[
                CommandHandler("cancel", handle_cancel),
            ],
        )

        # Support conversation (triggered by inline button)
        support_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(cb_support, pattern=CB_SUPPORT),
            ],
            states={
                SUP_WAITING_MESSAGE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        sup_receive_message,
                    ),
                ],
                SUP_WAITING_REPLY_CHOICE: [
                    CallbackQueryHandler(
                        sup_reply_tg, pattern=CB_SUP_REPLY_TG
                    ),
                    CallbackQueryHandler(
                        sup_reply_email, pattern=CB_SUP_REPLY_EMAIL
                    ),
                    CallbackQueryHandler(
                        sup_no_reply, pattern=CB_SUP_NO_REPLY
                    ),
                ],
                SUP_WAITING_EMAIL: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        sup_receive_email,
                    ),
                ],
            },
            fallbacks=[
                CommandHandler("cancel", handle_cancel),
            ],
        )

        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("help", cmd_help))
        app.add_handler(CommandHandler("stats", cmd_stats))
        app.add_handler(CommandHandler("restart", cmd_restart))
        app.add_handler(search_conv)
        # Keep support flow before trial flow so feedback text is routed
        # to Contact Support when both conversations are active.
        app.add_handler(support_conv)
        app.add_handler(trial_conv)
        app.add_handler(
            CallbackQueryHandler(cb_benefits, pattern=CB_BENEFITS)
        )
        app.add_handler(
            CallbackQueryHandler(cb_pricing, pattern=CB_PRICING)
        )
        app.add_handler(
            CallbackQueryHandler(cb_privacy, pattern=CB_PRIVACY)
        )
        app.add_handler(
            CallbackQueryHandler(
                cb_cancel_sub, pattern=CB_CANCEL_SUB
            )
        )
        app.add_handler(
            CallbackQueryHandler(
                cb_cancel_sub_confirm,
                pattern=CB_CANCEL_SUB_CONFIRM,
            )
        )
        app.add_handler(
            CallbackQueryHandler(
                cb_cancel_sub_abort,
                pattern=CB_CANCEL_SUB_ABORT,
            )
        )
        app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                handle_unknown,
            )
        )

        return app

    def run(self) -> None:
        """Start the bot in long-polling mode (blocking).

        Registers bot commands with Telegram so they appear in the
        menu, then enters the polling loop.
        """
        log.info(
            "Starting Telegram bot (allowed_ids=%s).",
            self.allowed_ids or "all",
        )
        app = self._build_application()

        async def _post_init(application: Application) -> None:
            await application.bot.set_my_commands(
                [
                    BotCommand("start", "Show main menu"),
                    BotCommand("help", "Show main menu"),
                    BotCommand("search", "Search for jobs"),
                    BotCommand("stats", "Show DB statistics"),
                    BotCommand("restart", "Restart & clear session"),
                    BotCommand("cancel", "Cancel current action"),
                ]
            )

        app.post_init = _post_init
        drop_pending_raw = os.environ.get(
            "TELEGRAM_DROP_PENDING_UPDATES",
            "false",
        ).strip().lower()
        drop_pending = drop_pending_raw in {"1", "true", "yes", "on"}

        # Keep retrying startup when Telegram API is temporarily unreachable.
        app.run_polling(
            drop_pending_updates=drop_pending,
            bootstrap_retries=-1,
        )
