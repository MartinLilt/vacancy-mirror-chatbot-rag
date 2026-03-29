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
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from backend.services.postgres import PostgresJobExportService

log = logging.getLogger(__name__)

# ── Conversation states ───────────────────────────────────────────────
WAITING_QUERY = 0


def _get_allowed_ids() -> set[int]:
    """Parse ALLOWED_USER_IDS env var into a set of ints."""
    raw = os.environ.get("ALLOWED_USER_IDS", "").strip()
    if not raw:
        return set()
    return {int(x.strip()) for x in raw.split(",") if x.strip()}


def _is_allowed(user_id: int, allowed: set[int]) -> bool:
    """Return True when the user is permitted to use the bot."""
    return not allowed or user_id in allowed


# ── Handlers ──────────────────────────────────────────────────────────

async def cmd_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle /start — greet the user."""
    allowed: set[int] = context.bot_data["allowed_ids"]
    user = update.effective_user
    if not _is_allowed(user.id, allowed):
        await update.message.reply_text(
            "⛔ You are not authorised to use this bot."
        )
        return

    text = (
        f"👋 Hello, *{user.first_name}*!\n\n"
        "I'm the *Vacancy Mirror* assistant.\n"
        "I can help you explore Upwork job clusters and vacancies.\n\n"
        "Commands:\n"
        "• /search — search for jobs by keyword\n"
        "• /stats — show database statistics\n"
        "• /help — show this message\n"
    )
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_help(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle /help."""
    await cmd_start(update, context)


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
        parse_mode=ParseMode.MARKDOWN,
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
        "🔍 What are you looking for?\n"
        "Send me a keyword or describe the kind of job "
        "(e.g. *React developer*, *data analyst*, *copywriter*).",
        parse_mode=ParseMode.MARKDOWN,
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

    query = update.message.text.strip()
    if not query:
        await update.message.reply_text(
            "⚠️ Please send a non-empty search term."
        )
        return WAITING_QUERY

    await update.message.chat.send_action(ChatAction.TYPING)

    db_service: PostgresJobExportService = context.bot_data["db"]
    try:
        jobs = db_service.search_jobs(query=query, limit=5)
    except Exception as exc:
        log.exception("Search failed for query %r: %s", query, exc)
        await update.message.reply_text(
            "❌ Search failed. Please try again later."
        )
        return ConversationHandler.END

    if not jobs:
        await update.message.reply_text(
            f"😕 No jobs found for *{query}*.\n"
            "Try different keywords.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"✅ Found *{len(jobs)}* matching jobs for *{query}*:",
        parse_mode=ParseMode.MARKDOWN,
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
            parse_mode=ParseMode.MARKDOWN,
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


async def handle_unknown(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Handle unrecognised messages outside a conversation."""
    await update.message.reply_text(
        "🤷 I didn't understand that. Use /help to see available commands."
    )


# ── Bot builder ───────────────────────────────────────────────────────

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

        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("help", cmd_help))
        app.add_handler(CommandHandler("stats", cmd_stats))
        app.add_handler(search_conv)
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

        # Register menu commands
        async def _post_init(application: Application) -> None:
            await application.bot.set_my_commands(
                [
                    BotCommand("start", "Start the bot"),
                    BotCommand("help", "Show help"),
                    BotCommand("search", "Search for jobs"),
                    BotCommand("stats", "Show DB statistics"),
                    BotCommand("cancel", "Cancel current action"),
                ]
            )

        app.post_init = _post_init
        app.run_polling(drop_pending_updates=True)
