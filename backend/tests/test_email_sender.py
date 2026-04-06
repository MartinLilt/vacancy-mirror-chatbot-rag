from __future__ import annotations

import unittest

from backend.services.email_sender import SendGridEmailSender


class _SpySender(SendGridEmailSender):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.used_smtp = False
        self.used_sendgrid = False

    def _send_via_smtp(self, *, to_email: str, subject: str, text: str) -> None:
        self.used_smtp = True

    def _send_via_sendgrid(self, *, to_email: str, subject: str, text: str) -> None:
        self.used_sendgrid = True


class EmailSenderTransportTest(unittest.TestCase):
    def test_prefers_smtp_when_configured(self) -> None:
        sender = _SpySender(
            smtp_host="smtp.office365.com",
            smtp_port=587,
            smtp_user="support@vacancy-mirror.com",
            smtp_password="secret",
            smtp_tls=True,
            api_key="sendgrid-key",
            from_email="support@vacancy-mirror.com",
        )
        sender.send_support_reply(
            to_email="user@example.com",
            subject="Support",
            text="Hello",
        )
        self.assertTrue(sender.used_smtp)
        self.assertFalse(sender.used_sendgrid)

    def test_uses_sendgrid_when_smtp_not_configured(self) -> None:
        sender = _SpySender(
            api_key="sendgrid-key",
            from_email="support@vacancy-mirror.com",
        )
        sender.send_support_reply(
            to_email="user@example.com",
            subject="Support",
            text="Hello",
        )
        self.assertFalse(sender.used_smtp)
        self.assertTrue(sender.used_sendgrid)

    def test_fails_without_any_transport(self) -> None:
        with self.assertRaises(ValueError):
            SendGridEmailSender(
                api_key="",
                smtp_host="",
                from_email="support@vacancy-mirror.com",
            )


if __name__ == "__main__":
    unittest.main()

