from __future__ import annotations

import unittest

from backend.services.stripe_webhook import _WebhookHandler


class ChatwootWebhookHelpersTest(unittest.TestCase):
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

