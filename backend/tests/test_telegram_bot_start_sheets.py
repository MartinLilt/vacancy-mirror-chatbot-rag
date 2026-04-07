from __future__ import annotations

import types
import unittest
from unittest.mock import Mock

from telegram.constants import ParseMode

from backend.services.telegram_bot import cmd_start


class _DummyMessage:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    async def reply_text(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.calls.append((args, kwargs))
        return None


class TelegramBotStartSheetsSyncTest(unittest.IsolatedAsyncioTestCase):
    async def test_start_syncs_sheets_even_if_db_calls_fail(self) -> None:
        user = types.SimpleNamespace(
            id=123,
            first_name="Alex",
            last_name="Doe",
            username="alexdoe",
        )
        message = _DummyMessage()
        update = types.SimpleNamespace(effective_user=user, message=message)

        db = Mock()
        db.get_subscription.return_value = {
            "plan": "plus",
            "status": "active",
            "stripe_customer_id": "cus_1",
            "stripe_subscription_id": "sub_1",
        }
        db.upsert_bot_user.side_effect = RuntimeError("db write down")
        db.get_user_for_sheet.side_effect = RuntimeError("db read down")

        sheets = Mock()
        context = types.SimpleNamespace(
            bot_data={
                "allowed_ids": {123},
                "db": db,
                "sheets": sheets,
            }
        )

        await cmd_start(update, context)

        sheets.upsert_user.assert_called_once()
        payload = sheets.upsert_user.call_args.args[0]
        self.assertEqual(payload["telegram_user_id"], 123)
        self.assertEqual(payload["first_name"], "Alex")
        self.assertEqual(payload["plan"], "plus")
        self.assertEqual(payload["status"], "active")
        self.assertEqual(payload["stripe_customer_id"], "cus_1")
        self.assertEqual(payload["stripe_subscription_id"], "sub_1")
        self.assertTrue(payload["last_updated"])
        self.assertEqual(len(message.calls), 1)

    async def test_start_preserves_first_seen_and_refreshes_last_updated(self) -> None:
        user = types.SimpleNamespace(
            id=42,
            first_name="Mila",
            last_name="",
            username="mila",
        )
        message = _DummyMessage()
        update = types.SimpleNamespace(effective_user=user, message=message)

        db = Mock()
        db.get_subscription.return_value = {
            "plan": "pro_plus",
            "status": "active",
            "stripe_customer_id": "cus_x",
            "stripe_subscription_id": "sub_x",
        }
        db.get_user_for_sheet.return_value = {
            "first_name": "Mila",
            "last_name": "Ivanova",
            "username": "mila",
            "plan": "pro_plus",
            "status": "active",
            "stripe_customer_id": "cus_x",
            "stripe_subscription_id": "sub_x",
            "first_seen": "2026-01-01 10:00:00",
            "last_updated": "2026-01-01 10:00:00",
        }

        sheets = Mock()
        context = types.SimpleNamespace(
            bot_data={
                "allowed_ids": {42},
                "db": db,
                "sheets": sheets,
            }
        )

        await cmd_start(update, context)

        sheets.upsert_user.assert_called_once()
        payload = sheets.upsert_user.call_args.args[0]
        self.assertEqual(payload["telegram_user_id"], 42)
        self.assertEqual(payload["first_seen"], "2026-01-01 10:00:00")
        self.assertTrue(payload["last_updated"])
        self.assertNotEqual(payload["last_updated"], "2026-01-01 10:00:00")
        self.assertEqual(len(message.calls), 1)

    async def test_start_escapes_first_name_for_markdown_v2(self) -> None:
        user = types.SimpleNamespace(
            id=777,
            first_name="Ann_[Dev](QA)!",
            last_name="",
            username="ann",
        )
        message = _DummyMessage()
        update = types.SimpleNamespace(effective_user=user, message=message)

        db = Mock()
        db.get_subscription.return_value = None
        db.get_user_for_sheet.return_value = None

        sheets = Mock()
        context = types.SimpleNamespace(
            bot_data={
                "allowed_ids": {777},
                "db": db,
                "sheets": sheets,
            }
        )

        await cmd_start(update, context)

        self.assertEqual(len(message.calls), 1)
        args, kwargs = message.calls[0]
        text = args[0]
        self.assertIn("Ann\\_\\[Dev\\]\\(QA\\)\\!", text)
        self.assertEqual(kwargs.get("parse_mode"), ParseMode.MARKDOWN_V2)


if __name__ == "__main__":
    unittest.main()

