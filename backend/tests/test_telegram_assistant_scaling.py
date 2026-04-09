from __future__ import annotations

import types
import unittest

from backend.services.telegram_bot import (
    AssistantRuntimeState,
    TRIAL_WAITING_QUERY,
    cmd_assistant_metrics,
    trial_receive_query,
)


class _DummyMessage:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.calls: list[tuple[tuple, dict]] = []
        self.last_thinking = None

    async def reply_text(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.calls.append((args, kwargs))
        self.last_thinking = _DummyThinking()
        return self.last_thinking

    async def _noop_edit(self, *_args, **_kwargs):
        return None


class _DummyDb:
    def count_bot_chat_requests_last_24h(self, _user_id: int) -> int:
        return 0

    def insert_bot_chat_request(self, **_kwargs) -> None:
        return None

    def get_subscription(self, _user_id: int):
        return None


class _DummyDbCountFails(_DummyDb):
    def count_bot_chat_requests_last_24h(self, _user_id: int) -> int:
        raise RuntimeError("db unavailable")


class _DummyThinking:
    def __init__(self) -> None:
        self.edits: list[tuple[str, dict]] = []

    async def edit_text(self, text: str, **kwargs):  # noqa: ANN003
        self.edits.append((text, kwargs))
        return None


class TelegramAssistantScalingTest(unittest.IsolatedAsyncioTestCase):
    async def test_trial_continues_when_usage_counter_fails(self) -> None:
        runtime = AssistantRuntimeState(max_concurrency=1)

        msg = _DummyMessage("hello")
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=555),
            message=msg,
        )
        context = types.SimpleNamespace(
            bot_data={
                "allowed_ids": {555},
                "db": _DummyDbCountFails(),
                "assistant_llm": types.SimpleNamespace(
                    answer_market_question=lambda **_kwargs: "ok",
                ),
                "assistant_orchestrator": None,
                "assistant_infer_client": None,
                "assistant_runtime": runtime,
                "assistant_per_user_guard_enabled": False,
                "assistant_acquire_timeout_sec": 0.01,
            },
            user_data={},
        )

        result = await trial_receive_query(update, context)
        self.assertEqual(result, TRIAL_WAITING_QUERY)
        self.assertIsNotNone(msg.last_thinking)
        edited_text = msg.last_thinking.edits[-1][0]
        self.assertIn("ok", edited_text)
        self.assertIn("Used 1/35", edited_text)

    async def test_trial_uses_degraded_reply_when_all_llm_paths_fail(self) -> None:
        runtime = AssistantRuntimeState(max_concurrency=1)

        def _raise_error(*_args, **_kwargs):  # noqa: ANN002, ANN003
            raise RuntimeError("provider down")

        msg = _DummyMessage("how to improve proposals")
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=444),
            message=msg,
        )
        context = types.SimpleNamespace(
            bot_data={
                "allowed_ids": {444},
                "db": _DummyDb(),
                "assistant_llm": types.SimpleNamespace(
                    answer_market_question=_raise_error,
                ),
                "assistant_orchestrator": None,
                "assistant_infer_client": None,
                "assistant_runtime": runtime,
                "assistant_per_user_guard_enabled": False,
                "assistant_acquire_timeout_sec": 0.01,
            },
            user_data={},
        )

        result = await trial_receive_query(update, context)
        self.assertEqual(result, TRIAL_WAITING_QUERY)
        self.assertIsNotNone(msg.last_thinking)
        edited_text = msg.last_thinking.edits[-1][0]
        self.assertIn("temporarily unavailable", edited_text)
        self.assertIn("Quick guidance from built-in knowledge", edited_text)

    async def test_trial_rejects_when_same_user_request_is_active(self) -> None:
        runtime = AssistantRuntimeState(max_concurrency=2)
        lock = runtime.lock_for_user(111)
        await lock.acquire()

        msg = _DummyMessage("hello")
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=111),
            message=msg,
        )
        context = types.SimpleNamespace(
            bot_data={
                "allowed_ids": {111},
                "db": _DummyDb(),
                "assistant_llm": types.SimpleNamespace(),
                "assistant_orchestrator": None,
                "assistant_runtime": runtime,
                "assistant_per_user_guard_enabled": True,
                "assistant_acquire_timeout_sec": 0.01,
            },
            user_data={},
        )

        result = await trial_receive_query(update, context)
        self.assertEqual(result, TRIAL_WAITING_QUERY)
        self.assertEqual(runtime.user_busy_rejections, 1)
        self.assertIn("still processing your previous message", msg.calls[0][0][0])

        lock.release()

    async def test_trial_rejects_when_global_capacity_is_exhausted(self) -> None:
        runtime = AssistantRuntimeState(max_concurrency=1)
        await runtime.semaphore.acquire()

        msg = _DummyMessage("hello")
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=222),
            message=msg,
        )
        context = types.SimpleNamespace(
            bot_data={
                "allowed_ids": {222},
                "db": _DummyDb(),
                "assistant_llm": types.SimpleNamespace(),
                "assistant_orchestrator": None,
                "assistant_runtime": runtime,
                "assistant_per_user_guard_enabled": False,
                "assistant_acquire_timeout_sec": 0.01,
            },
            user_data={},
        )

        result = await trial_receive_query(update, context)
        self.assertEqual(result, TRIAL_WAITING_QUERY)
        self.assertEqual(runtime.overload_rejections, 1)
        self.assertIn("High load", msg.calls[0][0][0])

        runtime.semaphore.release()

    async def test_assistant_metrics_command_returns_snapshot(self) -> None:
        runtime = AssistantRuntimeState(max_concurrency=4)
        runtime.active = 2
        runtime.completed = 10
        runtime.failed = 1
        runtime.overload_rejections = 3
        runtime.user_busy_rejections = 2
        runtime.route_fast_path = 6
        runtime.route_long_path = 3
        runtime.route_simple = 2
        runtime.total_latency_sec = 33.0

        msg = _DummyMessage()
        update = types.SimpleNamespace(
            effective_user=types.SimpleNamespace(id=333),
            message=msg,
        )
        context = types.SimpleNamespace(
            bot_data={
                "allowed_ids": {333},
                "assistant_runtime": runtime,
            }
        )

        await cmd_assistant_metrics(update, context)
        payload = msg.calls[0][0][0]
        self.assertIn("active: 2/4", payload)
        self.assertIn("completed: 10", payload)
        self.assertIn("routes fast/long/simple: 6/3/2", payload)


if __name__ == "__main__":
    unittest.main()

