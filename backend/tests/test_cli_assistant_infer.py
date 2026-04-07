from __future__ import annotations

import unittest

from backend.cli import build_parser


class CliAssistantInferCommandTest(unittest.TestCase):
    def test_assistant_infer_command_is_registered(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["assistant-infer", "--port", "19090"])
        self.assertEqual(args.command, "assistant-infer")
        self.assertEqual(args.port, 19090)
        self.assertTrue(callable(args.func))


if __name__ == "__main__":
    unittest.main()

