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

import logging
import os

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

from backend.services.postgres import PostgresJobExportService

log = logging.getLogger(__name__)

# -- Conversation states --------------------------------------------------
WAITING_QUERY = 0

# Support conversation states
SUP_WAITING_MESSAGE = 10
SUP_WAITING_REPLY_CHOICE = 11
SUP_WAITING_EMAIL = 12

# -- Callback data constants ---------------------------------------------
CB_CHAT = "cb_chat"
CB_BENEFITS = "cb_benefits"
CB_PRICING = "cb_pricing"
CB_SUPPORT = "cb_support"
CB_PRIVACY = "cb_privacy"

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
            callback_data=CB_BENEFITS,
        )],
        [InlineKeyboardButton(
            "💳 Pricing & subscription plans",
            callback_data=CB_PRICING,
        )],
        [InlineKeyboardButton(
            "🆘 Contact support                    ",
            callback_data=CB_SUPPORT,
        )],
        [InlineKeyboardButton(
            "🔒 Privacy policy & terms        ",
            callback_data=CB_PRIVACY,
        )],
    ])


# -- Handlers ------------------------------------------------------------

async def cmd_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle /start — greet the user with structured welcome."""
    allowed: set[int] = context.bot_data["allowed_ids"]
    user = update.effective_user
    if not _is_allowed(user.id, allowed):
        await update.message.reply_text(
            "⛔ You are not authorised to use this bot."
        )
        return

    text = (
        f"👋 *Welcome, {user.first_name}\\!*\n\n"

        "🪞 *Meet Vacancy Mirror*\n"
        "AI\\-powered freelance market intelligence\\.\n"
        "Stop guessing — start knowing\\. 🎯\n\n"

        "✅ *What you get:*\n"
        "🔍 Semantic job search — by meaning, not just keywords\n"
        "🧩 Role clusters — see who's actually hiring\n"
        "🤖 AI answers on skills, roles & market trends\n"
        "📈 Know what the market wants before you apply\n\n"

        "🔜 *Coming soon:*\n"
        "▸ LinkedIn & Freelancer\\.com data\n"
        "▸ Salary & rate benchmarks\n"
        "▸ Personalised market reports\n"
        "▸ Fiverr integration is under consideration\n\n"

        "📡 *Powered by:* Upwork\n\n"

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
) -> None:
    """Handle 'Chat with assistant' button."""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "💬 *Trial chat*\n\n"
        "Ask me anything about the job market ✍️\n\n"
        "_e\\.g\\. \"What skills do React devs need?\"_\n\n"
        "_tap /cancel to exit_",
        parse_mode=ParseMode.MARKDOWN_V2,
    )


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
            "Limit: 30 messages every 24 hours\\."
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
    """Handle 'Pricing' button — send three plans as a message burst."""
    query = update.callback_query
    await query.answer()

    # Stripe payment links — set via environment variables
    stripe_plus_url: str = os.environ.get(
        "STRIPE_PLUS_URL", "https://buy.stripe.com/plus"
    )
    stripe_pro_plus_url: str = os.environ.get(
        "STRIPE_PRO_PLUS_URL", "https://buy.stripe.com/pro_plus"
    )

    plans: list[str] = [
        (
            "💳 *Pricing & Subscription Plans*\n\n"
            "_All plans are billed monthly\\. "
            "Annual billing is not available\\._"
        ),
        (
            "🆓 *Free Plan*\n\n"
            "Everything you need to get started\\.\n\n"
            "Includes:\n"
            "▸ 📊 Weekly Freelance Trends Report\n"
            "▸ 💬 AI Market Assistant "
            "\\(limit: 30 messages every 24 hours\\)\n"
            "▸ 📈 Weekly Trend Charts\n\n"
            "_No payment required\\. Available to all users\\._"
        ),
        (
            "⭐ *Plus Plan* — monthly subscription\n\n"
            "Everything in Free, plus advanced profile tools\\.\n\n"
            "Includes:\n"
            "▸ 🎯 Profile Optimisation Expert\n"
            "▸ 🤖 Weekly Profile & Projects Agent\n"
            "   \\(up to 5 portfolio projects\\)\n\n"
            "_Vacancy Mirror does not access or modify your "
            "profile automatically\\. All recommendations are "
            "for you to apply manually\\._"
        ),
        (
            "🚀 *Pro Plus Plan* — monthly subscription\n\n"
            "Everything in Plus, with maximum coverage\\.\n\n"
            "Includes:\n"
            "▸ 🚀 Extended Projects Agent\n"
            "   \\(up to 12 portfolio projects\\)\n"
            "▸ 🏷️ Weekly Skills & Tags Report\n\n"
            "_Full portfolio coverage aligned with market "
            "trends every week\\._"
        ),
    ]

    for plan in plans:
        await query.message.reply_text(
            plan,
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    await query.message.reply_text(
        "� *Choose your plan and subscribe via Stripe:*",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "⭐ Subscribe to Plus",
                url=stripe_plus_url,
            )],
            [InlineKeyboardButton(
                "🚀 Subscribe to Pro Plus",
                url=stripe_pro_plus_url,
            )],
            [InlineKeyboardButton(
                "❓ Questions? Contact support",
                callback_data=CB_SUPPORT,
            )],
        ]),
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
    await _forward_to_admin(
        context=context,
        user=update.effective_user,
        reply_via="Telegram",
        extra=None,
    )
    await query.message.reply_text(
        "✅ *Message sent to support\\!*\n\n"
        "We will reply to you here in Telegram\\.\n"
        "Expect a response within *3 business days*\\. ⏳",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    context.user_data.pop("sup_message", None)
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
    await _forward_to_admin(
        context=context,
        user=update.effective_user,
        reply_via="email",
        extra=email,
    )
    await update.message.reply_text(
        "✅ *Message sent to support\\!*\n\n"
        f"We will reply to *{email}*\\.\n"
        "Expect a response within *3 business days*\\. ⏳",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    context.user_data.pop("sup_message", None)
    return ConversationHandler.END


async def sup_no_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """User does not need a reply — forward to admin and finish."""
    query = update.callback_query
    await query.answer()
    await _forward_to_admin(
        context=context,
        user=update.effective_user,
        reply_via=None,
        extra=None,
    )
    await query.message.reply_text(
        "✅ *Message sent to support\\!*\n\n"
        "Thank you for your feedback\\. 🙏",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    context.user_data.pop("sup_message", None)
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
        app.add_handler(support_conv)
        app.add_handler(
            CallbackQueryHandler(cb_chat, pattern=CB_CHAT)
        )
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
        app.run_polling(drop_pending_updates=True)
