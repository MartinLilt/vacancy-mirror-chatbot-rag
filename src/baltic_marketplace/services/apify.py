"""Apify service for Upwork job collection."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request


DEFAULT_UPWORK_JOB_SCRAPER_ACTOR = "upwork-vibe/upwork-job-scraper"


class ApifyServiceError(RuntimeError):
    """Raised when the Apify service cannot be configured or used."""


@dataclass(frozen=True)
class ApifyConfig:
    token: str
    actor_id: str | None = None

    @classmethod
    def from_env(cls) -> "ApifyConfig":
        token = os.getenv("APIFY_TOKEN", "").strip()
        actor_id = os.getenv("APIFY_ACTOR_ID", "").strip() or None
        if not token:
            raise ApifyServiceError("Переменная окружения APIFY_TOKEN не задана.")
        return cls(token=token, actor_id=actor_id)


class ApifyService:
    """Minimal Apify client for running Upwork job scraping actors."""

    def __init__(self, config: ApifyConfig) -> None:
        self._config = config

    @classmethod
    def from_env(cls) -> "ApifyService":
        return cls(ApifyConfig.from_env())

    @property
    def token(self) -> str:
        return self._config.token

    @property
    def actor_id(self) -> str | None:
        return self._config.actor_id

    def build_upwork_job_search_input(
        self,
        *,
        limit: int = 100,
        from_date: str | None = None,
        to_date: str | None = None,
        job_categories: list[str] | None = None,
        include_keywords: list[str] | None = None,
        exclude_keywords: list[str] | None = None,
    ) -> dict[str, Any]:
        if limit < 1:
            raise ApifyServiceError("limit должен быть больше 0.")

        payload: dict[str, Any] = {"limit": limit}

        if from_date:
            payload["fromDate"] = from_date
        if to_date:
            payload["toDate"] = to_date
        if job_categories:
            payload["jobCategories"] = job_categories

        include_terms = [term.strip() for term in (include_keywords or []) if term.strip()]
        if include_terms:
            payload["includeKeywords.keywords"] = include_terms
            payload["includeKeywords.matchTitle"] = True
            payload["includeKeywords.matchDescription"] = True
            payload["includeKeywords.matchSkills"] = True

        exclude_terms = [term.strip() for term in (exclude_keywords or []) if term.strip()]
        if exclude_terms:
            payload["excludeKeywords.keywords"] = exclude_terms
            payload["excludeKeywords.matchTitle"] = True
            payload["excludeKeywords.matchDescription"] = True
            payload["excludeKeywords.matchSkills"] = True

        return payload

    def normalize_actor_id(self, actor_id: str) -> str:
        normalized = actor_id.strip()
        if not normalized:
            raise ApifyServiceError("actor_id не должен быть пустым.")
        if "/" in normalized:
            owner, name = normalized.split("/", 1)
            if not owner or not name:
                raise ApifyServiceError("actor_id в формате owner/name задан некорректно.")
            return f"{owner}~{name}"
        return normalized

    def run_actor(
        self,
        *,
        actor_id: str,
        actor_input: dict[str, Any],
    ) -> list[dict[str, Any]]:
        normalized_actor_id = self.normalize_actor_id(actor_id)
        url = f"https://api.apify.com/v2/acts/{normalized_actor_id}/run-sync-get-dataset-items"
        query = parse.urlencode({"token": self.token})
        full_url = f"{url}?{query}"
        req = request.Request(
            full_url,
            data=_json_bytes(actor_input),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=180) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ApifyServiceError(f"Apify API вернул {exc.code}: {body}") from exc
        except error.URLError as exc:
            raise ApifyServiceError(f"Не удалось подключиться к Apify API: {exc.reason}") from exc

        try:
            data = _json_loads(raw)
        except ValueError as exc:
            raise ApifyServiceError("Apify API вернул невалидный JSON.") from exc
        if not isinstance(data, list):
            raise ApifyServiceError("Apify API вернул неожиданный формат ответа.")
        return [item for item in data if isinstance(item, dict)]

    def collect_upwork_jobs(
        self,
        *,
        limit: int = 100,
        from_date: str | None = None,
        to_date: str | None = None,
        job_categories: list[str] | None = None,
        include_keywords: list[str] | None = None,
        exclude_keywords: list[str] | None = None,
    ) -> dict[str, Any]:
        actor_id = self.actor_id or DEFAULT_UPWORK_JOB_SCRAPER_ACTOR
        actor_input = self.build_upwork_job_search_input(
            limit=limit,
            from_date=from_date,
            to_date=to_date,
            job_categories=job_categories,
            include_keywords=include_keywords,
            exclude_keywords=exclude_keywords,
        )
        items = self.run_actor(actor_id=actor_id, actor_input=actor_input)
        return {
            "source": "apify",
            "actor_id": actor_id,
            "count": len(items),
            "input": actor_input,
            "items": items,
        }


def _json_bytes(payload: dict[str, Any]) -> bytes:
    import json

    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _json_loads(raw: str) -> Any:
    import json

    return json.loads(raw)
