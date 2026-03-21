import unittest

from baltic_marketplace.analysis.drafts import FactSafeDraftRefiner


class FakeLLM:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_json(self, *, system_prompt, user_prompt):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
        )
        return self.response


class FactSafeDraftRefinerTests(unittest.TestCase):
    def test_refine_returns_wrapped_safe_draft(self):
        llm = FakeLLM(
            {
                "safety_notes": ["Removed unsupported metrics"],
                "post_title": "Safer draft",
                "hook": "A simpler hook",
                "body_sections": ["One", "Two"],
                "cta": "DM me",
                "hashtags": ["#AI"],
                "full_post": "Safe draft text",
                "asset_suggestion": "Simple screenshot",
            }
        )
        draft_payload = {"profileUrl": "https://www.linkedin.com/in/test", "draft": {"full_post": "x"}}
        profile_strategy = {"primary_goal": "Create interest"}
        recommendation = {"recommendation": {"recommended_direction": "Case study"}}

        result = FactSafeDraftRefiner(llm).refine(
            draft_payload=draft_payload,
            profile_strategy=profile_strategy,
            recommendation=recommendation,
        )

        self.assertEqual(result["profileUrl"], "https://www.linkedin.com/in/test")
        self.assertEqual(result["draft"]["post_title"], "Safer draft")
        self.assertEqual(result["draft"]["safety_notes"][0], "Removed unsupported metrics")


if __name__ == "__main__":
    unittest.main()
