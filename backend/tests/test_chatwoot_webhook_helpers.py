from __future__ import annotations

import unittest

from backend.services.integrations.stripe import (
    _WebhookHandler,
    _support_reply_email_text,
    _support_reply_telegram_text,
    _support_ticket_closed_email_text,
    _support_ticket_unpin_failed_telegram_text,
    _support_ticket_public_id,
)


class ChatwootWebhookHelpersTest(unittest.TestCase):
    def test_support_public_ticket_and_reply_text_format(self) -> None:
        self.assertEqual(_support_ticket_public_id(42), "VM-000016")  # 42 in base-36
        self.assertEqual(
            _support_reply_telegram_text(
                event_id=42,
                answer="Thanks for your request",
            ),
            (
                "🆘 Support reply from Vacancy Mirror:\n\n"
                "Ticket: VM-000016\n\n"
                "Answer:\n"
                "Thanks for your request"
            ),
        )
        self.assertEqual(
            _support_ticket_unpin_failed_telegram_text(event_id=42),
            (
                "ℹ️ Ticket closed, but I could not unpin the original ticket message automatically.\n"
                "Please unpin it manually if needed.\n\n"
                "Ticket: VM-000016"
            ),
        )
        self.assertEqual(
            _support_ticket_closed_email_text(event_id=42),
            (
                "Your support ticket has been closed.\n\n"
                "Ticket: VM-000016\n\n"
                "If you still need help, please contact support again."
            ),
        )
        self.assertEqual(
            _support_reply_email_text(
                event_id=42,
                answer="Thanks for your request",
            ),
            (
                "Support reply from Vacancy Mirror:\n\n"
                "Ticket: VM-000016\n\n"
                "Answer:\n"
                "Thanks for your request"
            ),
        )

    def test_public_agent_reply_is_detected(self) -> None:
        payload = {
            "event": "message_created",
            "message_type": "outgoing",
            "private": False,
            "sender": {"type": "agent", "name": "Support Agent"},
            "content": "Hello from support",
            "conversation": {"id": 42},
            "id": 1001,
        }
        self.assertTrue(_WebhookHandler._chatwoot_is_public_agent_reply(payload))

    def test_private_end_ticket_command_is_detected(self) -> None:
        close_payload = {
            "private": True,
            "content": "/end ticket resolved",
        }
        public_payload = {
            "private": False,
            "content": "/end ticket resolved",
        }
        self.assertTrue(
            _WebhookHandler._chatwoot_is_private_close_command(close_payload)
        )
        self.assertFalse(
            _WebhookHandler._chatwoot_is_private_close_command(public_payload)
        )

    def test_private_or_non_outgoing_is_ignored(self) -> None:
        private_payload = {
            "event": "message_created",
            "message_type": "outgoing",
            "private": True,
        }
        incoming_payload = {
            "event": "message_created",
            "message_type": "incoming",
            "private": False,
        }
        self.assertFalse(_WebhookHandler._chatwoot_is_public_agent_reply(private_payload))
        self.assertFalse(_WebhookHandler._chatwoot_is_public_agent_reply(incoming_payload))

    def test_extractors_return_expected_values(self) -> None:
        payload = {
            "content": "Top-level content",
            "conversation": {"id": 555},
            "id": "abc-1",
        }
        self.assertEqual(
            _WebhookHandler._chatwoot_message_content(payload),
            "Top-level content",
        )
        self.assertEqual(
            _WebhookHandler._chatwoot_conversation_id(payload),
            555,
        )
        self.assertEqual(
            _WebhookHandler._chatwoot_message_id(payload),
            "abc-1",
        )


if __name__ == "__main__":
    unittest.main()

