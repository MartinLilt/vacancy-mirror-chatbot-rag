import unittest

from baltic_marketplace.analysis.drafts import (
    FinalPolishRefiner,
    ImageHeadlineGenerator,
    LinkedInCompactRefiner,
    PostDraftGenerator,
)


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


class PostDraftGeneratorTests(unittest.TestCase):
    def test_generate_returns_wrapped_draft(self):
        llm = FakeLLM(
            {
                "post_title": "Case study",
                "hook": "We replaced 5 steps with 1 plugin.",
                "body_sections": ["Problem", "Solution", "Result"],
                "cta": "DM me if you want a pilot.",
                "hashtags": ["#AI", "#Webflow"],
                "full_post": "Full draft text",
                "asset_suggestion": "Use before/after screenshot",
            }
        )
        post_analysis = {
            "profileUrl": "https://www.linkedin.com/in/test",
            "analysis": {"profile_insights": {}},
        }
        profile_strategy = {"primary_goal": "Create interest"}
        recommendation = {
            "recommendation": {
                "recommended_direction": "Case study",
            }
        }

        result = PostDraftGenerator(llm).generate(
            post_analysis=post_analysis,
            profile_strategy=profile_strategy,
            recommendation=recommendation,
        )

        self.assertEqual(result["profileUrl"], "https://www.linkedin.com/in/test")
        self.assertEqual(result["draft"]["post_title"], "Case study")


class LinkedInCompactRefinerTests(unittest.TestCase):
    def test_refine_returns_wrapped_compact_draft(self):
        llm = FakeLLM(
            {
                "safety_notes": ["Compressed long paragraphs"],
                "post_title": "Compact draft",
                "hook": "Hook",
                "body_sections": ["One", "Two"],
                "cta": "Comment below",
                "hashtags": ["#AI"],
                "image_headline": "ONE PLUGIN",
                "image_subheadline": "Early concept",
                "full_post": "Compact post text",
                "asset_suggestion": "Single cover",
            }
        )
        draft_payload = {"profileUrl": "https://www.linkedin.com/in/test", "draft": {"full_post": "x"}}
        profile_strategy = {"primary_goal": "Create interest"}
        recommendation = {"recommendation": {"recommended_direction": "Case study"}}

        result = LinkedInCompactRefiner(llm).refine(
            draft_payload=draft_payload,
            profile_strategy=profile_strategy,
            recommendation=recommendation,
        )

        self.assertEqual(result["profileUrl"], "https://www.linkedin.com/in/test")
        self.assertEqual(result["draft"]["post_title"], "Compact draft")
        self.assertEqual(result["draft"]["image_headline"], "ONE PLUGIN")


class FinalPolishRefinerTests(unittest.TestCase):
    def test_refine_returns_wrapped_polished_draft(self):
        llm = FakeLLM(
            {
                "safety_notes": ["Polished phrasing"],
                "post_title": "Polished draft",
                "hook": "Hook",
                "body_sections": ["One", "Two"],
                "cta": "Comment below",
                "hashtags": ["#AI"],
                "image_headline": "LESS CHAOS",
                "image_subheadline": "Early concept",
                "full_post": "Polished post text",
                "asset_suggestion": "Single cover",
            }
        )
        draft_payload = {"profileUrl": "https://www.linkedin.com/in/test", "draft": {"full_post": "x"}}
        profile_strategy = {"primary_goal": "Create interest"}
        recommendation = {"recommendation": {"recommended_direction": "Case study"}}

        result = FinalPolishRefiner(llm).refine(
            draft_payload=draft_payload,
            profile_strategy=profile_strategy,
            recommendation=recommendation,
        )

        self.assertEqual(result["profileUrl"], "https://www.linkedin.com/in/test")
        self.assertEqual(result["draft"]["post_title"], "Polished draft")
        self.assertEqual(result["draft"]["image_headline"], "LESS CHAOS")


class ImageHeadlineGeneratorTests(unittest.TestCase):
    def test_generate_returns_headline_payload(self):
        llm = FakeLLM(
            {
                "image_headline": "ONE PLUGIN, FEWER HEADACHES",
                "image_subheadline": "Early Ammplug concept",
            }
        )
        draft_payload = {"profileUrl": "https://www.linkedin.com/in/test", "draft": {"full_post": "x"}}
        profile_strategy = {"primary_goal": "Create interest"}
        recommendation = {"recommendation": {"recommended_direction": "Case study"}}

        result = ImageHeadlineGenerator(llm).generate(
            draft_payload=draft_payload,
            profile_strategy=profile_strategy,
            recommendation=recommendation,
        )

        self.assertEqual(result["profileUrl"], "https://www.linkedin.com/in/test")
        self.assertEqual(result["image_headline"], "ONE PLUGIN, FEWER HEADACHES")


if __name__ == "__main__":
    unittest.main()
