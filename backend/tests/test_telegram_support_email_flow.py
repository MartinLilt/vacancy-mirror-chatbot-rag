from __future__ import annotations

import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

from telegram.constants import ParseMode
from telegram.ext import ConversationHandler

from backend.services.telegram_bot import _escape_markdown_v2, sup_receive_email


class _DummyMessage:
    def __init__(self, *, text: str, message_id: int) -> None:
        self.text = text
        self.message_id = message_id
        self.reply_calls: list[tuple[tuple, dict]] = []

    async def reply_text(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.reply_calls.append((args, kwargs))
        return None


class TelegramSupportEmailFlowTest(unittest.IsolatedAsyncioTestCase):
    def test_escape_markdown_v2_for_email(self) -> None:
        value = "john_doe+1@example-domain.com"
        self.assertEqual(
            _escape_markdown_v2(value),
            "john\\_doe\\+1@example\\-domain\\.com",
        )

    async def test_sup_receive_email_sends_confirmation_with_ticket_and_email(self) -> None:
        message = _DummyMessage(
            text="john_doe+1@example-domain.com",
            message_id=111,
        )
        user = types.SimpleNamespace(
            id=705456139,
            username="john",
            full_name="John Doe",
        )
        update = types.SimpleNamespace(
            message=message,
            effective_user=user,
            effective_chat=types.SimpleNamespace(id=999),
        )

        db = Mock()
        db.insert_support_feedback_event.return_value = 42

        fake_client = Mock()
        fake_client.create_support_conversation.return_value = {
            "conversation_id": 77,
            "contact_id": 88,
        }

        context = types.SimpleNamespace(
            bot_data={"db": db},
            user_data={
                "sup_message": "Need support",
                "sup_message_id": 222,
            },
        )

        with (
            patch("backend.services.telegram_bot.ChatwootSupportClient", return_value=fake_client),
            patch("backend.services.telegram_bot._pin_support_ticket_message", new=AsyncMock()),
        ):
            result = await sup_receive_email(update, context)

        self.assertEqual(result, ConversationHandler.END)
        self.assertEqual(len(message.reply_calls), 1)

        text = message.reply_calls[0][0][0]
        kwargs = message.reply_calls[0][1]
        self.assertIn("Expect a response within *3 business days*", text)
        self.assertIn("Ticket ID: `VM-000016`", text)
        self.assertIn("john\\_doe\\+1@example\\-domain\\.com", text)
        self.assertEqual(kwargs.get("parse_mode"), ParseMode.MARKDOWN_V2)


if __name__ == "__main__":
    unittest.main()

