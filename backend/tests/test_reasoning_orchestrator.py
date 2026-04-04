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
        self.assertIn("Conclusion:", result.final_answer)

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


if __name__ == "__main__":
    unittest.main()

