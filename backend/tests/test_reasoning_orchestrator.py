from __future__ import annotations

import unittest

from backend.services.reasoning_orchestrator import ReasoningOrchestrator


class _FakeRetriever:
    def retrieve(self, *, query: str, top_k: int = 4) -> list[object]:
        return [
            {
                "section_id": "policy",
                "title": "Policy",
                "content": "Use only public data and do not claim account access.",
            }
        ]

    def render_sections(self, sections: list[object]) -> str:
        return "[policy] Policy\nUse only public data and do not claim account access."


class _FakeLLM:
    def generate_structured_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> dict[str, object]:
        if "Layer 1" in system_prompt:
            assert "Retrieved sections:" in user_prompt
            return {
                "context_summary": "User asks about React demand.",
                "checklist": [
                    "Explain current React demand trend",
                    "List practical skills to focus on",
                ],
            }
        if "Layer 2" in system_prompt:
            if "Explain current React demand trend" in user_prompt:
                return {
                    "action_plan": "Summarize trend direction",
                    "answer_summary": "React demand remains strong in web projects.",
                }
            if "List practical skills to focus on" in user_prompt:
                return {
                    "action_plan": "Provide concrete skill list",
                    "answer_summary": "Focus on TypeScript, Next.js, testing, and API integration.",
                }
            return {
                "action_plan": "Fallback plan",
                "answer_summary": "Fallback summary.",
            }
        if "Layer 3" in system_prompt:
            return {
                "final_answer": "React is still in demand; prioritize production-ready frontend skills.",
                "conclusion": "Build portfolio projects with measurable outcomes.",
            }
        raise AssertionError("Unexpected layer prompt")


class _FastPathLLM:
    def generate_structured_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> dict[str, object]:
        if "Layer 1" in system_prompt:
            return {
                "route": "fast_path",
                "context_summary": "Simple FAQ question.",
                "fast_answer": "Free plan includes 35 messages per 24 hours.",
                "risk_level": "low",
                "needs_multi_step": False,
                "intent_confidence": 0.95,
                "grounding_confidence": 0.9,
            }
        raise AssertionError("Fast-path flow should not call Layer 2 or Layer 3")


class _FastPathEscalatedLLM:
    def generate_structured_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> dict[str, object]:
        if "Layer 1" in system_prompt:
            return {
                "route": "fast_path",
                "context_summary": "Potentially risky answer.",
                "fast_answer": "Short answer that should be rejected.",
                "risk_level": "high",
                "needs_multi_step": True,
                "intent_confidence": 0.45,
                "grounding_confidence": 0.4,
                "checklist": [
                    "Provide safe grounded answer",
                ],
            }
        if "Layer 2" in system_prompt:
            return {
                "action_plan": "Use grounded policy data",
                "answer_summary": "A safer, grounded answer requires a brief reasoning step.",
            }
        if "Layer 3" in system_prompt:
            return {
                "final_answer": "Here is a grounded response based on the available policy sections.",
                "conclusion": "Use the long-path result when risk is elevated.",
            }
        raise AssertionError("Unexpected layer prompt")


class _NoChecklistLayer1LLM:
    def generate_structured_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> dict[str, object]:
        if "Layer 1" in system_prompt:
            return {
                "route": "long_path",
                "context_summary": "Missing checklist in this response.",
            }
        if "Layer 2" in system_prompt:
            return {
                "action_plan": "Use fallback checklist item",
                "answer_summary": "Grounded concise answer summary.",
            }
        if "Layer 3" in system_prompt:
            return {
                "final_answer": "Final grounded response without checklist failure.",
            }
        raise AssertionError("Unexpected layer prompt")


class ReasoningOrchestratorTest(unittest.TestCase):
    def test_three_layer_flow_returns_final_answer(self) -> None:
        orchestrator = ReasoningOrchestrator(
            llm=_FakeLLM(),
            retriever=_FakeRetriever(),
        )
        result = orchestrator.run(
            question="What should I learn for React freelance jobs?",
            history=[{"role": "user", "content": "I am moving from vanilla JS."}],
        )

        self.assertEqual(len(result.checklist), 2)
        self.assertEqual(len(result.step_summaries), 2)
        self.assertIn("React is still in demand", result.final_answer)
        self.assertNotIn("Conclusion:", result.final_answer)

    def test_stage_callback_order(self) -> None:
        orchestrator = ReasoningOrchestrator(
            llm=_FakeLLM(),
            retriever=_FakeRetriever(),
        )
        stages: list[str] = []

        orchestrator.run(
            question="What should I learn for React freelance jobs?",
            history=[{"role": "user", "content": "I am moving from vanilla JS."}],
            stage_callback=stages.append,
        )

        self.assertEqual(
            stages,
            ["layer1_start", "layer2_start", "layer3_start"],
        )

    def test_fast_path_returns_immediate_answer(self) -> None:
        orchestrator = ReasoningOrchestrator(
            llm=_FastPathLLM(),
            retriever=_FakeRetriever(),
        )
        stages: list[str] = []

        result = orchestrator.run(
            question="What is the free trial limit?",
            history=[],
            stage_callback=stages.append,
        )

        self.assertEqual(result.route, "fast_path")
        self.assertEqual(result.checklist, [])
        self.assertEqual(result.step_summaries, [])
        self.assertIn("35 messages", result.final_answer)
        self.assertEqual(stages, ["layer1_start", "fast_path_start"])

    def test_fast_path_escalates_to_long_path_when_signals_are_unsafe(self) -> None:
        orchestrator = ReasoningOrchestrator(
            llm=_FastPathEscalatedLLM(),
            retriever=_FakeRetriever(),
        )
        stages: list[str] = []

        result = orchestrator.run(
            question="Give me a quick but risky answer",
            history=[],
            stage_callback=stages.append,
        )

        self.assertEqual(result.route, "long_path")
        self.assertEqual(len(result.checklist), 1)
        self.assertIn("grounded response", result.final_answer)
        self.assertEqual(stages, ["layer1_start", "layer2_start", "layer3_start"])

    def test_missing_layer1_checklist_uses_fallback_item(self) -> None:
        orchestrator = ReasoningOrchestrator(
            llm=_NoChecklistLayer1LLM(),
            retriever=_FakeRetriever(),
        )
        stages: list[str] = []

        result = orchestrator.run(
            question="Help me quickly",
            history=[],
            stage_callback=stages.append,
        )

        self.assertEqual(result.route, "long_path")
        self.assertEqual(len(result.checklist), 1)
        self.assertIn("concise, grounded answer", result.checklist[0])
        self.assertIn("Final grounded response", result.final_answer)
        self.assertEqual(stages, ["layer1_start", "layer2_start", "layer3_start"])


if __name__ == "__main__":
    unittest.main()

