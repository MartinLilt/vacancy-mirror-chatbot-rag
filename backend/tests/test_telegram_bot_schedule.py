from __future__ import annotations

import types
import unittest

from telegram.constants import ParseMode

from backend.services.telegram_bot import cmd_schedule


class _DummyMessage:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    async def reply_text(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.calls.append((args, kwargs))
        return None


class TelegramBotScheduleTest(unittest.IsolatedAsyncioTestCase):
    async def test_schedule_sends_weekly_plan_for_allowed_user(self) -> None:
        user = types.SimpleNamespace(id=123)
        message = _DummyMessage()
        update = types.SimpleNamespace(effective_user=user, message=message)
        context = types.SimpleNamespace(bot_data={"allowed_ids": {123}})

        await cmd_schedule(update, context)

        self.assertEqual(len(message.calls), 1)
        args, kwargs = message.calls[0]
        text = args[0]
        self.assertIn("Monday — Top Trends chart \\(Free\\)", text)
        self.assertIn("Tuesday — Top 10 Roles \\(Plus\\)", text)
        self.assertIn("Wednesday — Top 20 Technologies \\(Plus\\)", text)
        self.assertIn("Thursday — Top 10 Profile Optimisation Tips \\(Free\\)", text)
        self.assertIn("Friday — Top 20 Skills \\(Free\\)", text)
        self.assertEqual(kwargs.get("parse_mode"), ParseMode.MARKDOWN_V2)

    async def test_schedule_skips_message_for_not_allowed_user(self) -> None:
        user = types.SimpleNamespace(id=999)
        message = _DummyMessage()
        update = types.SimpleNamespace(effective_user=user, message=message)
        context = types.SimpleNamespace(bot_data={"allowed_ids": {123}})

        await cmd_schedule(update, context)

        self.assertEqual(message.calls, [])


if __name__ == "__main__":
    unittest.main()

