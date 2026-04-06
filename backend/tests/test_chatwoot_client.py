from __future__ import annotations

import unittest
from typing import Any

from backend.services.chatwoot_client import ChatwootSupportClient


class _FakeChatwootClient(ChatwootSupportClient):
    def __init__(self) -> None:
        super().__init__(
            base_url="http://chatwoot.local",
            account_id=1,
            inbox_id=2,
            api_access_token="token",
            timeout_seconds=5,
        )
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _request_json(  # type: ignore[override]
        self,
        *,
        method: str,
        path: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append((path, payload))
        if path == "contacts":
            return {
                "id": 10,
                "payload": {
                    "contact_inbox": {"source_id": "source-10"},
                },
            }
        if path == "conversations":
            return {"id": 20}
        if path == "conversations/20/messages":
            return {"id": 30}
        raise AssertionError(f"Unexpected path: {path}")


class ChatwootClientTest(unittest.TestCase):
    def test_initial_message_contains_public_ticket_id_and_operator_notes(self) -> None:
        client = _FakeChatwootClient()

        result = client.create_support_conversation(
            event_id=4,
            telegram_user_id=705456139,
            telegram_username="@limi_amm",
            telegram_full_name="Martin Li",
            reply_channel="telegram",
            feedback_message="This is test of the telegram support func.",
        )

        self.assertEqual(result["contact_id"], 10)
        self.assertEqual(result["conversation_id"], 20)

        message_payload = client.calls[-1][1]
        content = message_payload["content"]

        self.assertIn("Support event ID: 4", content)
        self.assertIn("Public ticket ID: VM-000004", content)
        self.assertIn("Send a PUBLIC reply", content)
        self.assertIn("PRIVATE note `/end ticket ...`", content)


if __name__ == "__main__":
    unittest.main()

