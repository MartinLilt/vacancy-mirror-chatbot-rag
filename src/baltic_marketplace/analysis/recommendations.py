"""Recommendation layer for the LinkedIn assistant."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from baltic_marketplace.openai_api.service import OpenAIService


class NextPostRecommender:
    """Generates the next-post recommendation from analysis + strategy."""

    def __init__(self, llm: OpenAIService) -> None:
        self._llm = llm

    def recommend(
        self,
        *,
        post_analysis: dict[str, Any],
        profile_strategy: dict[str, Any],
        engagement_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        analysis = post_analysis.get("analysis")
        if not isinstance(analysis, dict):
            raise ValueError("post_analysis must contain an 'analysis' object.")

        user_prompt = json.dumps(
            {
                "profile_url": post_analysis.get("profileUrl"),
                "post_count": post_analysis.get("post_count"),
                "post_analysis": analysis,
                "profile_strategy": profile_strategy,
                "engagement_context": engagement_context or {},
            },
            ensure_ascii=False,
            indent=2,
        )

        system_prompt = (
            "You are the strategy and recommendation layer for a LinkedIn assistant. "
            "Use the post analysis and the explicit business strategy to recommend the single best next LinkedIn post direction. "
            "Return JSON only. "
            "Prioritize commercial relevance to Ammplug, but keep the recommendation audience-friendly, non-hype, and aligned with the allowed CTA style. "
            "Use the engagement context to understand which existing post themes, framing patterns, and tones already resonated best. "
            "When possible, borrow the stronger engagement direction and adapt it toward Ammplug's product story. "
            "If one topic clearly outperformed others, prefer a next-post angle that bridges that stronger topic with Ammplug instead of drifting into a weaker theme. "
            "Respect the current business stage in the strategy. If the product is still early, avoid recommending strong conversion CTAs like pilot/demo invites unless the strategy explicitly allows them. "
            "Prefer concrete, understandable post directions over abstract thought pieces when the goal is warming up audience interest. "
            "Treat the current stage as audience warm-up, not launch-mode selling, unless the strategy explicitly says otherwise. "
            "Favor post ideas that make people react, agree, comment, or remember the product direction. "
            "Do not default to direct asks like 'comment pilot', 'book demo', or 'DM for access' if the strategy disallows them. "
            "Make the direction product-adjacent and easy to visualize: a situation, a problem, a contrast, a simple scenario, or a clear business takeaway. "
            "If you use numbers in the recommendation, they should be presented only as example framing or illustrative comparisons unless they are confirmed in the input. "
            "When numbers are useful, include them as clearly illustrative examples because they improve clarity and performance on LinkedIn. "
            "If the strategy allows a lightly ironic or witty tone, you may include a sharp metaphor, dry humor, or a mildly ironic comparison that makes the post feel more alive. "
            "Keep humor controlled, intelligent, and professional. "
            "JSON schema: "
            "{"
            "\"recommended_direction\":string,"
            "\"why_this_now\":string,"
            "\"target_audience\":string,"
            "\"post_goal\":string,"
            "\"post_type\":string,"
            "\"content_pillar\":string,"
            "\"stage_fit\":string,"
            "\"hook_options\":[string],"
            "\"key_points\":[string],"
            "\"cta\":string,"
            "\"success_signal\":string"
            "}"
        )

        recommendation = self._llm.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        return {
            "profileUrl": post_analysis.get("profileUrl"),
            "recommendation": recommendation,
        }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_engagement_context(
    *,
    posts_dataset: dict[str, Any],
    post_analysis: dict[str, Any],
    limit: int = 3,
) -> dict[str, Any]:
    posts = posts_dataset.get("posts")
    analysis = post_analysis.get("analysis")
    if not isinstance(posts, list):
        raise ValueError("posts_dataset must contain a 'posts' list.")
    if not isinstance(analysis, dict):
        raise ValueError("post_analysis must contain an 'analysis' object.")

    summaries = analysis.get("post_summaries")
    if not isinstance(summaries, list):
        raise ValueError("post_analysis.analysis must contain a 'post_summaries' list.")

    summary_by_id: dict[str, dict[str, Any]] = {}
    for item in summaries:
        if isinstance(item, dict):
            item_id = item.get("id")
            if isinstance(item_id, str):
                summary_by_id[item_id] = item

    ranked_posts: list[dict[str, Any]] = []
    topic_scores: dict[str, dict[str, Any]] = {}

    for post in posts:
        if not isinstance(post, dict):
            continue
        post_id = post.get("id")
        if not isinstance(post_id, str):
            continue
        summary = summary_by_id.get(post_id, {})
        likes = int(post.get("likes") or 0)
        comments = int(post.get("comments") or 0)
        score = likes + comments * 2
        topic = summary.get("main_topic") if isinstance(summary, dict) else None
        hook_type = summary.get("hook_type") if isinstance(summary, dict) else None
        text = str(post.get("text") or "").strip()
        hook_excerpt = text.splitlines()[0] if text else ""

        ranked_posts.append(
            {
                "id": post_id,
                "score": score,
                "likes": likes,
                "comments": comments,
                "main_topic": topic,
                "hook_type": hook_type,
                "hook_excerpt": hook_excerpt,
            }
        )

        if isinstance(topic, str) and topic:
            bucket = topic_scores.setdefault(
                topic,
                {"topic": topic, "score": 0, "posts": 0, "likes": 0, "comments": 0},
            )
            bucket["score"] += score
            bucket["posts"] += 1
            bucket["likes"] += likes
            bucket["comments"] += comments

    ranked_posts.sort(key=lambda item: item["score"], reverse=True)
    top_posts = ranked_posts[:limit]
    top_topics = sorted(topic_scores.values(), key=lambda item: item["score"], reverse=True)[:limit]

    return {
        "top_posts": top_posts,
        "top_topics": top_topics,
        "best_signal": top_posts[0] if top_posts else {},
    }
