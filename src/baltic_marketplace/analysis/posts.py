"""Post analysis layer for the LinkedIn assistant."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from baltic_marketplace.openai_api.service import OpenAIService


class PostAnalyzer:
    """Analyzes normalized LinkedIn posts using an LLM."""

    def __init__(self, llm: OpenAIService) -> None:
        self._llm = llm

    def analyze_dataset(self, dataset: dict[str, Any]) -> dict[str, Any]:
        posts = dataset.get("posts")
        if not isinstance(posts, list) or not posts:
            raise ValueError("Dataset must contain a non-empty 'posts' list.")

        user_prompt = json.dumps(
            {
                "profile_url": dataset.get("profileUrl"),
                "posts": posts,
            },
            ensure_ascii=False,
            indent=2,
        )

        system_prompt = (
            "You are analyzing a founder's LinkedIn posts for a future content strategy assistant. "
            "Return JSON only. "
            "For each post, compress the post into a clear semantic summary and identify the main topic, "
            "hook style, CTA style, target audience, and strategic value. "
            "Then provide overall profile-level insights and recommendations for the next content direction. "
            "JSON schema: "
            "{"
            "\"post_summaries\":[{"
            "\"id\":string,"
            "\"summary\":string,"
            "\"main_topic\":string,"
            "\"hook_type\":string,"
            "\"cta_type\":string,"
            "\"target_audience\":string,"
            "\"strategic_value\":string"
            "}],"
            "\"profile_insights\":{"
            "\"content_pillars\":[string],"
            "\"tone_traits\":[string],"
            "\"strong_patterns\":[string],"
            "\"weak_patterns\":[string],"
            "\"recommended_direction\":string,"
            "\"next_post_angles\":[string]"
            "}"
            "}"
        )

        analysis = self._llm.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        return {
            "source": dataset.get("source"),
            "profileUrl": dataset.get("profileUrl"),
            "post_count": len(posts),
            "analysis": analysis,
        }


def load_dataset(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
