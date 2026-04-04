"""Minimal OpenAI helpers for profile naming."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request


class OpenAIProfileNamingService:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.timeout_seconds = timeout_seconds or int(os.getenv("OPENAI_TIMEOUT_SECONDS", "180"))
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required.")

    def name_profiles(self, *, profiles: list[dict[str, Any]]) -> dict[str, Any]:
        payload = self._build_payload(profiles)
        body = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You name job-market role clusters. "
                        "Return strict JSON only. "
                        "Use concise, professional, human-readable role names. "
                        "Avoid hype words, hiring boilerplate, and generic filler."
                    ),
                },
                {"role": "user", "content": payload},
            ],
            "temperature": 0.2,
        }
        response = self._post_chat_completions(body)
        return self._parse_response_json(response)

    def _build_payload(self, profiles: list[dict[str, Any]]) -> str:
        lines = [
            "Name these job clusters.",
            "Return JSON with shape:",
            '{"profiles":[{"cluster_id":12,"role_name":"Full-Stack Developer","reason":"short reason"}]}',
            "Use the evidence from sample_titles, top_title_terms, and top_skill_phrases.",
            "If a cluster is WordPress support or Elementor-focused, say so directly.",
            "If a cluster is MERN or Full-Stack React, say so directly.",
            "Do not invent specializations not supported by the evidence.",
            "",
            json.dumps({"profiles": profiles}, ensure_ascii=False, indent=2),
        ]
        return "\n".join(lines)

    def _post_chat_completions(self, body: dict[str, Any]) -> dict[str, Any]:
        req = request.Request(
            url="https://api.openai.com/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API error: {exc.code} {detail}") from exc

    def _parse_response_json(self, response: dict[str, Any]) -> dict[str, Any]:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("OpenAI response does not contain choices.")
        message = choices[0].get("message", {})
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OpenAI response does not contain message content.")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"OpenAI response is not valid JSON: {content}") from exc


class OpenAIMarketAssistantService:
    """Simple OpenAI chat helper for market Q&A."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.timeout_seconds = timeout_seconds or int(
            os.getenv("OPENAI_TIMEOUT_SECONDS", "180")
        )
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required.")

    def answer_market_question(self, *, question: str) -> str:
        return self.generate_text(
            system_prompt=(
                "You are a freelance market assistant. "
                "Give practical, concise, factual answers. "
                "If data is uncertain, say so clearly. "
                "Respond in English only."
            ),
            user_prompt=question.strip(),
            temperature=0.4,
        )

    def generate_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.4,
    ) -> str:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        response = self._post_chat_completions(body)
        return self._extract_message_content(response)

    def generate_structured_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        body = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        response = self._post_chat_completions(body)
        content = self._extract_message_content(response)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"OpenAI response is not valid JSON: {content}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("OpenAI structured response must be a JSON object.")
        return parsed

    def _extract_message_content(self, response: dict[str, Any]) -> str:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("OpenAI response does not contain choices.")
        content = choices[0].get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OpenAI response does not contain message content.")
        return content.strip()

    def _post_chat_completions(self, body: dict[str, Any]) -> dict[str, Any]:
        req = request.Request(
            url="https://api.openai.com/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API error: {exc.code} {detail}") from exc
