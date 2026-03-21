"""Minimal OpenAI Responses API client."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request


DEFAULT_OPENAI_MODEL = "gpt-5-mini"


class OpenAIServiceError(RuntimeError):
    """Raised when the OpenAI service cannot complete a request."""


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str
    model: str
    timeout_seconds: int = 120

    @classmethod
    def from_env(cls, *, default_model: str | None = None) -> "OpenAIConfig":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise OpenAIServiceError("Переменная окружения OPENAI_API_KEY не задана.")

        model = default_model or os.getenv("OPENAI_MODEL", "").strip() or DEFAULT_OPENAI_MODEL
        timeout_raw = os.getenv("OPENAI_TIMEOUT_SECONDS", "120").strip() or "120"

        try:
            timeout_seconds = int(timeout_raw)
        except ValueError as exc:
            raise OpenAIServiceError(
                "OPENAI_TIMEOUT_SECONDS должен быть целым числом."
            ) from exc

        return cls(api_key=api_key, model=model, timeout_seconds=timeout_seconds)


class OpenAIService:
    """Thin wrapper around the OpenAI Responses API."""

    def __init__(self, config: OpenAIConfig) -> None:
        self._config = config

    @classmethod
    def from_env(cls, *, default_model: str | None = None) -> "OpenAIService":
        return cls(OpenAIConfig.from_env(default_model=default_model))

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return self.generate_json_from_user_content(
            system_prompt=system_prompt,
            user_content=[{"type": "input_text", "text": user_prompt}],
        )

    def generate_json_from_image_paths(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[str | Path],
    ) -> dict[str, Any]:
        user_content: list[dict[str, Any]] = [{"type": "input_text", "text": user_prompt}]
        for image_path in image_paths:
            user_content.append(
                {
                    "type": "input_image",
                    "image_url": _image_path_to_data_url(image_path),
                }
            )

        return self.generate_json_from_user_content(
            system_prompt=system_prompt,
            user_content=user_content,
        )

    def generate_json_from_user_content(
        self,
        *,
        system_prompt: str,
        user_content: list[dict[str, Any]],
    ) -> dict[str, Any]:
        body = {
            "model": self._config.model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
            "text": {"format": {"type": "json_object"}},
        }

        req = request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self._config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise OpenAIServiceError(
                f"OpenAI API вернул {exc.code}: {body}"
            ) from exc
        except error.URLError as exc:
            raise OpenAIServiceError(
                f"Не удалось подключиться к OpenAI API: {exc.reason}"
            ) from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OpenAIServiceError("OpenAI API вернул невалидный JSON.") from exc

        text = _extract_output_text(payload)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise OpenAIServiceError(
                "Модель вернула невалидный JSON для structured analysis."
            ) from exc


def _image_path_to_data_url(path: str | Path) -> str:
    image_path = Path(path)
    mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def _extract_output_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = payload.get("output")
    if not isinstance(output, list):
        raise OpenAIServiceError("OpenAI API вернул ответ без output_text.")

    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                return text

    raise OpenAIServiceError("Не удалось извлечь text output из ответа OpenAI API.")
