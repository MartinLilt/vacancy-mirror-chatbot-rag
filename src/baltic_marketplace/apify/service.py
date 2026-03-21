"""Apify service layer."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request


DEFAULT_APIFY_ACTOR_ID = "benjarapi/linkedin-user-posts"


class ApifyServiceError(RuntimeError):
    """Raised when the Apify service cannot complete a request."""


@dataclass(frozen=True)
class ApifyConfig:
    token: str
    actor_id: str
    timeout_seconds: int = 300

    @classmethod
    def from_env(cls, *, default_actor_id: str | None = None) -> "ApifyConfig":
        token = os.getenv("APIFY_TOKEN", "").strip()
        if not token:
            raise ApifyServiceError("Переменная окружения APIFY_TOKEN не задана.")

        actor_id = (
            default_actor_id
            or os.getenv("APIFY_ACTOR_ID", "").strip()
            or DEFAULT_APIFY_ACTOR_ID
        )
        timeout_raw = os.getenv("APIFY_TIMEOUT_SECONDS", "300").strip() or "300"

        try:
            timeout_seconds = int(timeout_raw)
        except ValueError as exc:
            raise ApifyServiceError(
                "APIFY_TIMEOUT_SECONDS должен быть целым числом."
            ) from exc

        return cls(
            token=token,
            actor_id=actor_id,
            timeout_seconds=timeout_seconds,
        )


class ApifyClient:
    """Minimal HTTP client for running Apify actors."""

    def __init__(self, config: ApifyConfig) -> None:
        self._config = config

    def run_actor_sync(self, input_payload: dict[str, Any]) -> list[dict[str, Any]]:
        actor_path = self._config.actor_id.replace("/", "~")
        query = parse.urlencode({"timeout": self._config.timeout_seconds})
        url = (
            f"https://api.apify.com/v2/acts/{actor_path}/run-sync-get-dataset-items"
            f"?{query}"
        )
        req = request.Request(
            url,
            data=json.dumps(input_payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._config.token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self._config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ApifyServiceError(
                f"Apify API вернул {exc.code} для actor {self._config.actor_id}: {body}"
            ) from exc
        except error.URLError as exc:
            raise ApifyServiceError(
                f"Не удалось подключиться к Apify API: {exc.reason}"
            ) from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ApifyServiceError("Apify API вернул невалидный JSON.") from exc

        if not isinstance(data, list):
            raise ApifyServiceError(
                "Apify actor вернул неожиданный формат ответа: ожидался список items."
            )

        return data


class ApifyService:
    """High-level operations for Apify-backed scraping flows."""

    def __init__(self, client: ApifyClient) -> None:
        self._client = client

    @classmethod
    def from_env(cls, *, default_actor_id: str | None = None) -> "ApifyService":
        return cls(ApifyClient(ApifyConfig.from_env(default_actor_id=default_actor_id)))

    def fetch_linkedin_profile_posts(
        self,
        *,
        profile_url: str,
        max_posts: int,
    ) -> dict[str, Any]:
        normalized_url = _normalize_profile_url(profile_url)
        if not normalized_url:
            raise ApifyServiceError("Параметр --profile-url обязателен.")
        if max_posts < 1:
            raise ApifyServiceError("Параметр --max-posts должен быть больше 0.")

        input_payload = _build_actor_input(
            actor_id=self._client._config.actor_id,
            profile_url=normalized_url,
            max_posts=max_posts,
        )
        items = self._client.run_actor_sync(input_payload)
        return {
            "source": "apify",
            "actorId": self._client._config.actor_id,
            "profileUrl": normalized_url,
            "items": items,
        }

    def fetch_linkedin_profile_post_summaries(
        self,
        *,
        profile_url: str,
        max_posts: int,
    ) -> list[dict[str, Any]]:
        payload = self.fetch_linkedin_profile_posts(
            profile_url=profile_url,
            max_posts=max_posts,
        )
        return [_summarize_post(item) for item in payload["items"]]

    def fetch_linkedin_profile_post_dataset(
        self,
        *,
        profile_url: str,
        max_posts: int,
    ) -> dict[str, Any]:
        payload = self.fetch_linkedin_profile_posts(
            profile_url=profile_url,
            max_posts=max_posts,
        )
        return {
            "source": payload["source"],
            "actorId": payload["actorId"],
            "profileUrl": payload["profileUrl"],
            "posts": [_normalize_post(item) for item in payload["items"]],
        }


def _normalize_profile_url(profile_url: str | None) -> str | None:
    if not profile_url:
        return None

    cleaned = profile_url.strip()
    if not cleaned:
        return None

    parts = parse.urlsplit(cleaned)
    scheme = parts.scheme or "https"
    netloc = parts.netloc or "www.linkedin.com"
    path = parts.path.rstrip("/")
    if not path:
        return None

    return parse.urlunsplit((scheme.lower(), netloc.lower(), path, "", ""))


def _build_actor_input(
    *,
    actor_id: str,
    profile_url: str,
    max_posts: int,
) -> dict[str, Any]:
    normalized_actor_id = actor_id.strip().lower()
    if normalized_actor_id == "benjarapi/linkedin-user-posts":
        return {
            "profile": profile_url,
            "maxPosts": max_posts,
        }

    return {
        "urls": [profile_url],
        "maxPosts": max_posts,
        "proxyConfiguration": {"useApifyProxy": False},
    }


def _summarize_post(item: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_post(item)

    return {
        "text": normalized["text"],
        "likes": normalized["likes"],
        "comments": normalized["comments"],
        "image_url": normalized["image_url"],
    }


def _normalize_post(item: dict[str, Any]) -> dict[str, Any]:
    stats = item.get("stats") or {}
    media = item.get("media") or {}
    posted_at = item.get("posted_at") or {}
    urn = item.get("urn") or {}

    return {
        "id": item.get("full_urn") or urn.get("activity_urn") or item.get("url"),
        "text": item.get("text") or "",
        "url": item.get("url"),
        "posted_at": posted_at.get("date"),
        "posted_timestamp": posted_at.get("timestamp"),
        "likes": int(stats.get("total_reactions") or 0),
        "comments": int(stats.get("comments") or 0),
        "image_url": _extract_image_url(media),
    }


def _extract_image_url(media: dict[str, Any]) -> str | None:
    direct_url = media.get("url")
    if isinstance(direct_url, str) and direct_url.strip():
        return direct_url

    images = media.get("images")
    if isinstance(images, list):
        for image in images:
            if not isinstance(image, dict):
                continue
            image_url = image.get("url")
            if isinstance(image_url, str) and image_url.strip():
                return image_url

    return None
