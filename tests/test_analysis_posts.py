import unittest

from baltic_marketplace.analysis.posts import PostAnalyzer


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


class PostAnalyzerTests(unittest.TestCase):
    def test_analyze_dataset_returns_wrapped_analysis(self):
        llm = FakeLLM(
            {
                "post_summaries": [
                    {
                        "id": "1",
                        "summary": "Summary",
                        "main_topic": "AI",
                        "hook_type": "Question",
                        "cta_type": "Discussion",
                        "target_audience": "Founders",
                        "strategic_value": "Thought leadership",
                    }
                ],
                "profile_insights": {
                    "content_pillars": ["AI"],
                    "tone_traits": ["expert"],
                    "strong_patterns": ["question-led hooks"],
                    "weak_patterns": ["low CTA variety"],
                    "recommended_direction": "More founder-focused AI operations content",
                    "next_post_angles": ["AI office for SaaS founders"],
                },
            }
        )
        dataset = {
            "source": "apify",
            "profileUrl": "https://www.linkedin.com/in/test",
            "posts": [
                {
                    "id": "1",
                    "text": "Post text",
                    "likes": 2,
                    "comments": 1,
                }
            ],
        }

        analysis = PostAnalyzer(llm).analyze_dataset(dataset)

        self.assertEqual(analysis["source"], "apify")
        self.assertEqual(analysis["post_count"], 1)
        self.assertEqual(
            analysis["analysis"]["profile_insights"]["recommended_direction"],
            "More founder-focused AI operations content",
        )


if __name__ == "__main__":
    unittest.main()
