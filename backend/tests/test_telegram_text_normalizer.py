from __future__ import annotations

import unittest

from backend.services.bot.telegram import (
    _normalize_telegram_text,
    _strip_telegram_markdown,
)


class TelegramTextNormalizerTest(unittest.TestCase):
    def test_normalizer_removes_conclusion_heading(self) -> None:
        raw = (
            "Main points:\n"
            "- first\n"
            "- second\n\n"
            "Conclusion: Keep it short."
        )
        result = _normalize_telegram_text(raw)
        self.assertIn("• first", result)
        self.assertIn("• second", result)
        self.assertNotIn("Conclusion:", result)
        self.assertIn("Keep it short.", result)

    def test_strip_markdown_fallback_keeps_readable_text(self) -> None:
        raw = "**Title**\n_useful_ `code` [docs](https://example.com)"
        result = _strip_telegram_markdown(raw)
        self.assertIn("Title", result)
        self.assertIn("useful", result)
        self.assertIn("code", result)
        self.assertIn("docs (https://example.com)", result)


if __name__ == "__main__":
    unittest.main()

