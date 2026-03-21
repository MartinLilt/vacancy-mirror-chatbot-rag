import unittest

from baltic_marketplace.analysis.recommendations import NextPostRecommender


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


class NextPostRecommenderTests(unittest.TestCase):
    def test_recommend_returns_wrapped_payload(self):
        llm = FakeLLM(
            {
                "recommended_direction": "Show a practical plugin case study",
                "why_this_now": "It aligns with product interest",
                "target_audience": "Digital agencies",
                "post_goal": "Generate partnership interest",
                "post_type": "Case study",
                "content_pillar": "AI-assisted plugins",
                "hook_options": ["What if one plugin replaced 3 tools?"],
                "key_points": ["Time savings", "Lower dev cost"],
                "cta": "DM me if you want early access",
                "success_signal": "Partnership interest",
            }
        )
        post_analysis = {
            "profileUrl": "https://www.linkedin.com/in/test",
            "analysis": {"profile_insights": {"recommended_direction": "x"}},
        }
        profile_strategy = {"primary_goal": "Create product interest"}

        result = NextPostRecommender(llm).recommend(
            post_analysis=post_analysis,
            profile_strategy=profile_strategy,
        )

        self.assertEqual(result["profileUrl"], "https://www.linkedin.com/in/test")
        self.assertEqual(
            result["recommendation"]["post_type"],
            "Case study",
        )


if __name__ == "__main__":
    unittest.main()
