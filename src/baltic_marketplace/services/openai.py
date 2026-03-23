"""Minimal OpenAI service for LLM-based market pattern classification."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request


DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"


class OpenAIServiceError(RuntimeError):
    """Raised when the OpenAI service cannot be configured or used."""


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str
    model: str = DEFAULT_OPENAI_MODEL

    @classmethod
    def from_env(cls) -> "OpenAIConfig":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        model = os.getenv("OPENAI_MODEL", "").strip() or DEFAULT_OPENAI_MODEL
        if not api_key:
            raise OpenAIServiceError("Переменная окружения OPENAI_API_KEY не задана.")
        return cls(api_key=api_key, model=model)


class OpenAIService:
    """Small wrapper around the OpenAI Responses API."""

    def __init__(self, config: OpenAIConfig) -> None:
        self._config = config

    @classmethod
    def from_env(cls) -> "OpenAIService":
        return cls(OpenAIConfig.from_env())

    @property
    def model(self) -> str:
        return self._config.model

    def classify_market_patterns(
        self,
        *,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = _build_pattern_classification_prompt(payload)
        body = {
            "model": self.model,
            "input": prompt,
            "text": {"format": {"type": "json_object"}},
        }
        response = self._post_responses(body)
        output_text = self._extract_output_text(response)
        try:
            data = _loads_json_object(output_text)
        except ValueError as exc:
            raise OpenAIServiceError("OpenAI вернул невалидный JSON для классификации паттернов.") from exc
        return data

    def _post_responses(self, body: dict[str, Any]) -> dict[str, Any]:
        req = request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._config.api_key}",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=180) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            raise OpenAIServiceError(f"OpenAI API вернул {exc.code}: {body_text}") from exc
        except error.URLError as exc:
            raise OpenAIServiceError(f"Не удалось подключиться к OpenAI API: {exc.reason}") from exc

        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise OpenAIServiceError("OpenAI API вернул невалидный JSON.") from exc
        if not isinstance(data, dict):
            raise OpenAIServiceError("OpenAI API вернул неожиданный формат ответа.")
        return data

    def _extract_output_text(self, response: dict[str, Any]) -> str:
        output = response.get("output")
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for content_item in content:
                    if not isinstance(content_item, dict):
                        continue
                    if content_item.get("type") == "output_text":
                        text = content_item.get("text")
                        if isinstance(text, str) and text.strip():
                            parts.append(text)
            if parts:
                return "\n".join(parts)

        fallback = response.get("output_text")
        if isinstance(fallback, str) and fallback.strip():
            return fallback
        raise OpenAIServiceError("OpenAI API не вернул output_text.")


def _build_pattern_classification_prompt(payload: dict[str, Any]) -> str:
    return (
        "You are classifying Upwork market patterns for segment discovery.\n"
        "Classify each phrase or skill into exactly one label:\n"
        "- segment_signal: strong marker of a real market role, segment, or niche\n"
        "- supporting_signal: useful context, delivery style, stack, or adjacent clue\n"
        "- boilerplate: generic hiring language, application instructions, or platform filler\n"
        "- noise: weak, ambiguous, or too generic to help with segmentation\n\n"
        "Prioritize title_bigrams, title_trigrams, description_bigrams, description_trigrams.\n"
        "Treat skills as validation, not the main segmentation layer.\n"
        "Return valid JSON only with this shape:\n"
        "{\n"
        '  "summary": {\n'
        '    "top_segment_candidates": [\n'
        '      {"name": "...", "reason": "...", "source_patterns": ["..."]}\n'
        "    ],\n"
        '    "notes": ["..."]\n'
        "  },\n"
        '  "sections": {\n'
        '    "title_bigrams": [{"value": "...", "label": "...", "reason": "...", "normalized_cluster": "..."}],\n'
        '    "title_trigrams": [{"value": "...", "label": "...", "reason": "...", "normalized_cluster": "..."}],\n'
        '    "description_bigrams": [{"value": "...", "label": "...", "reason": "...", "normalized_cluster": "..."}],\n'
        '    "description_trigrams": [{"value": "...", "label": "...", "reason": "...", "normalized_cluster": "..."}],\n'
        '    "skills": [{"value": "...", "label": "...", "reason": "...", "normalized_cluster": "..."}]\n'
        "  }\n"
        "}\n\n"
        "Input JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _loads_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object.")
    return data
