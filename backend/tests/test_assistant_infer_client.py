from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.services.assistant_infer_client import AssistantInferClient


class AssistantInferClientTest(unittest.TestCase):
    def test_from_raw_urls_returns_none_for_empty(self) -> None:
        self.assertIsNone(AssistantInferClient.from_raw_urls(""))
        self.assertIsNone(AssistantInferClient.from_raw_urls(" , "))

    def test_round_robin_url_order(self) -> None:
        client = AssistantInferClient(base_urls=["http://a", "http://b", "http://c"])
        self.assertEqual(client._next_urls(), ["http://a", "http://b", "http://c"])
        self.assertEqual(client._next_urls(), ["http://b", "http://c", "http://a"])
        self.assertEqual(client._next_urls(), ["http://c", "http://a", "http://b"])

    def test_generate_answer_tries_next_replica_on_failure(self) -> None:
        client = AssistantInferClient(base_urls=["http://a", "http://b"])

        class _Resp:
            def __init__(self, payload: str) -> None:
                self._payload = payload.encode("utf-8")

            def read(self) -> bytes:
                return self._payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        calls = {"n": 0}

        def _fake_urlopen(req, timeout=0):  # noqa: ANN001, ANN003
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("first replica down")
            return _Resp('{"answer":"ok","route":"fast_path"}')

        with patch("backend.services.assistant_infer_client.request.urlopen", side_effect=_fake_urlopen):
            answer, route = client.generate_answer(question="q", history=[])

        self.assertEqual(answer, "ok")
        self.assertEqual(route, "fast_path")
        self.assertEqual(calls["n"], 2)


if __name__ == "__main__":
    unittest.main()

