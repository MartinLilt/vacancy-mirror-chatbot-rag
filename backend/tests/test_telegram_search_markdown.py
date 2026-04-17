from __future__ import annotations

import types
import unittest
from unittest.mock import Mock

from telegram.constants import ParseMode
from telegram.ext import ConversationHandler

from backend.services.bot.telegram import WAITING_QUERY, handle_search_query


class _DummyChat:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def send_action(self, action: str) -> None:
        self.actions.append(action)


class _DummyMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.chat = _DummyChat()
        self.calls: list[tuple[tuple, dict]] = []

    async def reply_text(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.calls.append((args, kwargs))
        return None


class TelegramBotSearchMarkdownTest(unittest.IsolatedAsyncioTestCase):
    async def test_no_results_escapes_query_for_markdown_v2(self) -> None:
        message = _DummyMessage("React_[Lead](TS)!")
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=501),
            message=message,
        )

        db = Mock()
        db.search_jobs.return_value = []
        context = types.SimpleNamespace(
            bot_data={
                "allowed_ids": {501},
                "db": db,
            }
        )

        state = await handle_search_query(update, context)

        self.assertEqual(state, ConversationHandler.END)
        self.assertEqual(len(message.calls), 1)
        args, kwargs = message.calls[0]
        self.assertIn("React\\_\\[Lead\\]\\(TS\\)\\!", args[0])
        self.assertEqual(kwargs.get("parse_mode"), ParseMode.MARKDOWN_V2)

    async def test_results_escape_dynamic_fields_for_markdown_v2(self) -> None:
        message = _DummyMessage("Py_[Bot](v2)!")
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=777),
            message=message,
        )

        db = Mock()
        db.search_jobs.return_value = [
            {
                "title": "Senior_[ML](Engineer)!",
                "category_name": "AI_[R&D](Lab)!",
                "uid": "abc_def(1)!",
            }
        ]
        context = types.SimpleNamespace(
            bot_data={
                "allowed_ids": {777},
                "db": db,
            }
        )

        state = await handle_search_query(update, context)

        self.assertEqual(state, ConversationHandler.END)
        self.assertEqual(len(message.calls), 2)

        summary_text = message.calls[0][0][0]
        self.assertIn("Py\\_\\[Bot\\]\\(v2\\)\\!", summary_text)
        self.assertEqual(
            message.calls[0][1].get("parse_mode"),
            ParseMode.MARKDOWN_V2,
        )

        job_text = message.calls[1][0][0]
        self.assertIn("Senior\\_\\[ML\\]\\(Engineer\\)\\!", job_text)
        self.assertIn("AI\\_\\[R&D\\]\\(Lab\\)\\!", job_text)
        self.assertIn("https://www\\.upwork\\.com/jobs/\\~abc\\_def\\(1\\)\\!", job_text)
        self.assertIn("Link:", job_text)
        self.assertEqual(
            message.calls[1][1].get("parse_mode"),
            ParseMode.MARKDOWN_V2,
        )

    async def test_empty_query_still_returns_waiting_state(self) -> None:
        message = _DummyMessage("   ")
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=99),
            message=message,
        )
        context = types.SimpleNamespace(
            bot_data={
                "allowed_ids": {99},
                "db": Mock(),
            }
        )

        state = await handle_search_query(update, context)

        self.assertEqual(state, WAITING_QUERY)
        self.assertEqual(len(message.calls), 1)
        self.assertIn("non-empty search term", message.calls[0][0][0])


if __name__ == "__main__":
    unittest.main()
