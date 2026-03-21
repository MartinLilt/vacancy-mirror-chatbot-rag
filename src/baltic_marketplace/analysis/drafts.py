"""Draft generation layer for the LinkedIn assistant."""

from __future__ import annotations

import json
from typing import Any

from baltic_marketplace.openai_api.service import OpenAIService


class PostDraftGenerator:
    """Generates a LinkedIn post draft from prior pipeline layers."""

    def __init__(self, llm: OpenAIService) -> None:
        self._llm = llm

    def generate(
        self,
        *,
        post_analysis: dict[str, Any],
        profile_strategy: dict[str, Any],
        recommendation: dict[str, Any],
        engagement_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        recommendation_payload = recommendation.get("recommendation")
        analysis_payload = post_analysis.get("analysis")
        if not isinstance(recommendation_payload, dict):
            raise ValueError("recommendation must contain a 'recommendation' object.")
        if not isinstance(analysis_payload, dict):
            raise ValueError("post_analysis must contain an 'analysis' object.")

        user_prompt = json.dumps(
            {
                "profile_url": post_analysis.get("profileUrl"),
                "post_analysis": analysis_payload,
                "profile_strategy": profile_strategy,
                "recommendation": recommendation_payload,
                "engagement_context": engagement_context or {},
            },
            ensure_ascii=False,
            indent=2,
        )

        system_prompt = (
            "You are the draft generation layer for a LinkedIn assistant. "
            "Write one LinkedIn post draft that follows the recommendation exactly, matches the strategy, "
            "and stays simple, commercially relevant, and non-hype. "
            "Return JSON only. "
            "The writing should be accessible to non-technical readers, but still feel credible to founders and digital agencies. "
            "Use the engagement context to borrow the stronger thematic pull, hook style, and emotional angle from the best-performing past posts. "
            "Do not be aggressive. Do not use fake urgency. "
            "Respect the business stage from the strategy. If the product is still early, do not write as if the product is broadly live or ready for hard conversion. "
            "Avoid abstract language when a clearer concrete framing is possible. "
            "Prefer concrete scenes, simple contrasts, easy-to-imagine workflows, and direct business-facing explanations. "
            "The post should warm up the audience and create interest, not push for immediate pilot/demo conversion unless the strategy explicitly allows that CTA. "
            "Favor comment-friendly or curiosity-driven CTAs over sales CTAs when the strategy indicates an early product stage. "
            "Write in a native LinkedIn style: short paragraphs, visible rhythm, strong opening line, very low filler, and fast-scanning structure. "
            "Prefer punchy lines over dense paragraphs. Keep the idea clear within the first 3 to 5 lines. "
            "Use the following structure by default: 1 strong hook, then a few very short standalone paragraphs or bullet-like lines, then a short closing takeaway, then CTA. "
            "Keep most paragraphs to 1 or 2 sentences. "
            "One idea per paragraph. "
            "Use line breaks aggressively to create rhythm. "
            "Do not write essay-style transitions or thick explanatory blocks. "
            "Actively use numbers when they help explain the point, but frame them as example, hypothetical, illustrative, or directional unless they are confirmed facts in the input. "
            "Aim for a compact LinkedIn format: usually 1 short hook, 3 to 6 short body blocks or bullets, and a short CTA. "
            "Create a strong metaphor-led opening line whenever possible. "
            "If the strategy supports it, add light irony, dry humor, or a witty phrase to make the post feel alive. "
            "Use at most one or two such touches. Keep them sharp, professional, and believable. "
            "Also generate an image headline system for the cover asset: one short punchy in-image headline and one tiny clarifying subtitle. "
            "The image headline should usually echo the hook, but in tighter headline form. "
            "JSON schema: "
            "{"
            "\"post_title\":string,"
            "\"hook\":string,"
            "\"body_sections\":[string],"
            "\"cta\":string,"
            "\"hashtags\":[string],"
            "\"image_headline\":string,"
            "\"image_subheadline\":string,"
            "\"full_post\":string,"
            "\"asset_suggestion\":string"
            "}"
        )

        draft = self._llm.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        return {
            "profileUrl": post_analysis.get("profileUrl"),
            "draft": draft,
        }


class FactSafeDraftRefiner:
    """Refines a generated draft into a fact-safe version."""

    def __init__(self, llm: OpenAIService) -> None:
        self._llm = llm

    def refine(
        self,
        *,
        draft_payload: dict[str, Any],
        profile_strategy: dict[str, Any],
        recommendation: dict[str, Any],
        engagement_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        draft = draft_payload.get("draft")
        recommendation_payload = recommendation.get("recommendation")
        if not isinstance(draft, dict):
            raise ValueError("draft_payload must contain a 'draft' object.")
        if not isinstance(recommendation_payload, dict):
            raise ValueError("recommendation must contain a 'recommendation' object.")

        user_prompt = json.dumps(
            {
                "draft": draft,
                "profile_strategy": profile_strategy,
                "recommendation": recommendation_payload,
                "engagement_context": engagement_context or {},
            },
            ensure_ascii=False,
            indent=2,
        )

        system_prompt = (
            "You are the fact-safe refinement layer for a LinkedIn assistant. "
            "Rewrite the draft so it is safe to publish without inventing facts. "
            "Remove or soften any unverified numbers, client scenarios, named plugin examples, case-study claims, or operational metrics unless they are clearly confirmed in the provided input. "
            "Keep the post commercially useful, simple, audience-friendly, and aligned with the strategy. "
            "If a strong claim is unsupported, replace it with a truthful and general phrasing. "
            "If numbers are useful for explanation, you should preserve them when they are clearly labeled as example, hypothetical, illustrative, directional, or scenario-based rather than factual measured outcomes. "
            "Respect the business stage in the strategy and avoid CTAs that push for a mature product action too early. "
            "If the strategy says the product is still early, do not use pilot/demo/availability CTAs unless explicitly allowed. "
            "Prefer engagement CTAs such as opinion, reaction, curiosity, or discussion if that better matches the strategy. "
            "Preserve a strong LinkedIn rhythm: short lines, low filler, easy scanning, and a visible structure. "
            "Keep the post compact and publish-ready, not essay-like. "
            "Break long explanations into short standalone lines or micro-paragraphs. "
            "One idea per paragraph. "
            "Do not allow dense 4-6 sentence blocks unless absolutely necessary. "
            "Preserve or improve the image headline and subtitle so the cover stays punchy and aligned with the post hook. "
            "Preserve any good light irony, dry humor, or witty contrast if it strengthens the post without undermining credibility. "
            "Remove jokes only if they feel forced, juvenile, or too meme-like. "
            "Do not use fake urgency. "
            "Return JSON only. "
            "JSON schema: "
            "{"
            "\"safety_notes\":[string],"
            "\"post_title\":string,"
            "\"hook\":string,"
            "\"body_sections\":[string],"
            "\"cta\":string,"
            "\"hashtags\":[string],"
            "\"image_headline\":string,"
            "\"image_subheadline\":string,"
            "\"full_post\":string,"
            "\"asset_suggestion\":string"
            "}"
        )

        refined = self._llm.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        return {
            "profileUrl": draft_payload.get("profileUrl"),
            "draft": refined,
        }


class LinkedInCompactRefiner:
    """Compresses a safe draft into a sharper LinkedIn-native format."""

    def __init__(self, llm: OpenAIService) -> None:
        self._llm = llm

    def refine(
        self,
        *,
        draft_payload: dict[str, Any],
        profile_strategy: dict[str, Any],
        recommendation: dict[str, Any],
        engagement_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        draft = draft_payload.get("draft")
        recommendation_payload = recommendation.get("recommendation")
        if not isinstance(draft, dict):
            raise ValueError("draft_payload must contain a 'draft' object.")
        if not isinstance(recommendation_payload, dict):
            raise ValueError("recommendation must contain a 'recommendation' object.")

        user_prompt = json.dumps(
            {
                "draft": draft,
                "profile_strategy": profile_strategy,
                "recommendation": recommendation_payload,
                "engagement_context": engagement_context or {},
            },
            ensure_ascii=False,
            indent=2,
        )

        system_prompt = (
            "You are the final LinkedIn compact refinement layer. "
            "Take a fact-safe draft and make it feel publish-ready for LinkedIn. "
            "Return JSON only. "
            "Your job is not to invent new claims, but to compress, sharpen, and improve rhythm. "
            "Preserve safety, stage alignment, and factual caution. "
            "Make the post faster to scan: strong first line, short standalone paragraphs, almost no filler, one idea per paragraph. "
            "Prefer 4 to 7 short body blocks total. "
            "Keep useful illustrative numbers if they improve clarity and are clearly labeled as illustrative. "
            "Keep light irony, wit, or metaphor if it strengthens the post. "
            "Do not turn the writing into essay prose. "
            "Do not add hard conversion CTAs if the strategy does not allow them. "
            "Preserve or improve image headline and subtitle so they stay punchy and tightly aligned with the hook. "
            "JSON schema: "
            "{"
            "\"safety_notes\":[string],"
            "\"post_title\":string,"
            "\"hook\":string,"
            "\"body_sections\":[string],"
            "\"cta\":string,"
            "\"hashtags\":[string],"
            "\"image_headline\":string,"
            "\"image_subheadline\":string,"
            "\"full_post\":string,"
            "\"asset_suggestion\":string"
            "}"
        )

        refined = self._llm.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        return {
            "profileUrl": draft_payload.get("profileUrl"),
            "draft": refined,
        }


class FinalPolishRefiner:
    """Applies a final publish-ready polish without changing the core meaning."""

    def __init__(self, llm: OpenAIService) -> None:
        self._llm = llm

    def refine(
        self,
        *,
        draft_payload: dict[str, Any],
        profile_strategy: dict[str, Any],
        recommendation: dict[str, Any],
        engagement_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        draft = draft_payload.get("draft")
        recommendation_payload = recommendation.get("recommendation")
        if not isinstance(draft, dict):
            raise ValueError("draft_payload must contain a 'draft' object.")
        if not isinstance(recommendation_payload, dict):
            raise ValueError("recommendation must contain a 'recommendation' object.")

        user_prompt = json.dumps(
            {
                "draft": draft,
                "profile_strategy": profile_strategy,
                "recommendation": recommendation_payload,
                "engagement_context": engagement_context or {},
            },
            ensure_ascii=False,
            indent=2,
        )

        system_prompt = (
            "You are the final polish layer for a LinkedIn assistant. "
            "Take a compact LinkedIn draft and make it feel sharp, natural, and founder-authentic. "
            "Return JSON only. "
            "Do not change the core message or invent new facts. "
            "Improve phrasing, remove synthetic wording, tighten transitions, and make the opening line more magnetic when possible. "
            "Keep the writing compact, high-signal, and ready to publish. "
            "Preserve illustrative-number framing, stage alignment, and non-hype tone. "
            "Preserve or improve any good metaphor, light irony, or witty contrast. "
            "Preserve image headline and subtitle if they are already strong; only improve them if they feel generic or weak. "
            "JSON schema: "
            "{"
            "\"safety_notes\":[string],"
            "\"post_title\":string,"
            "\"hook\":string,"
            "\"body_sections\":[string],"
            "\"cta\":string,"
            "\"hashtags\":[string],"
            "\"image_headline\":string,"
            "\"image_subheadline\":string,"
            "\"full_post\":string,"
            "\"asset_suggestion\":string"
            "}"
        )

        refined = self._llm.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        return {
            "profileUrl": draft_payload.get("profileUrl"),
            "draft": refined,
        }


class ImageHeadlineGenerator:
    """Generates a dedicated image headline/subheadline pair for the cover."""

    def __init__(self, llm: OpenAIService) -> None:
        self._llm = llm

    def generate(
        self,
        *,
        draft_payload: dict[str, Any],
        profile_strategy: dict[str, Any],
        recommendation: dict[str, Any],
        engagement_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        draft = draft_payload.get("draft")
        recommendation_payload = recommendation.get("recommendation")
        if not isinstance(draft, dict):
            raise ValueError("draft_payload must contain a 'draft' object.")
        if not isinstance(recommendation_payload, dict):
            raise ValueError("recommendation must contain a 'recommendation' object.")

        user_prompt = json.dumps(
            {
                "draft": draft,
                "profile_strategy": profile_strategy,
                "recommendation": recommendation_payload,
                "engagement_context": engagement_context or {},
            },
            ensure_ascii=False,
            indent=2,
        )

        system_prompt = (
            "You are the image headline layer for a LinkedIn cover generator. "
            "Generate one punchy in-image headline and one tiny clarifying subtitle. "
            "Return JSON only. "
            "The headline should be short, hooky, metaphor-led when possible, and suitable for a visual cover. "
            "The subtitle should be tiny, clarifying, and never stronger than the headline. "
            "Avoid hard claims unless confirmed. "
            "Avoid sounding generic, corporate, or too technical. "
            "Keep the pair aligned with the post hook and stage of the product. "
            "JSON schema: "
            "{"
            "\"image_headline\":string,"
            "\"image_subheadline\":string"
            "}"
        )

        payload = self._llm.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        return {
            "profileUrl": draft_payload.get("profileUrl"),
            "image_headline": payload.get("image_headline", ""),
            "image_subheadline": payload.get("image_subheadline", ""),
        }
