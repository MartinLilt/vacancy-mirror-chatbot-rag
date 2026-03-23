"""Upwork GraphQL service for job collection."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request


UPWORK_GRAPHQL_URL = "https://api.upwork.com/graphql"
UPWORK_OAUTH_TOKEN_URL = "https://www.upwork.com/api/v3/oauth2/token"
DEFAULT_SEARCH_QUERY = "web development"
DEFAULT_PAGE_SIZE = 50


class UpworkServiceError(RuntimeError):
    """Raised when the Upwork service cannot be configured or used."""


@dataclass(frozen=True)
class UpworkConfig:
    access_token: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    refresh_token: str | None = None

    @classmethod
    def from_env(cls) -> "UpworkConfig":
        access_token = os.getenv("UPWORK_ACCESS_TOKEN", "").strip() or None
        client_id = os.getenv("UPWORK_CLIENT_ID", "").strip() or None
        client_secret = os.getenv("UPWORK_CLIENT_SECRET", "").strip() or None
        refresh_token = os.getenv("UPWORK_REFRESH_TOKEN", "").strip() or None
        if access_token:
            return cls(
                access_token=access_token,
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
            )
        if client_id and client_secret and refresh_token:
            return cls(
                access_token=None,
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
            )
        if client_id and client_secret:
            return cls(
                access_token=None,
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=None,
            )
        raise UpworkServiceError(
            "Нужен UPWORK_ACCESS_TOKEN или набор UPWORK_CLIENT_ID/UPWORK_CLIENT_SECRET[/UPWORK_REFRESH_TOKEN]."
        )


class UpworkService:
    """Minimal Upwork GraphQL client for marketplace job search."""

    def __init__(self, config: UpworkConfig) -> None:
        self._config = config

    @classmethod
    def from_env(cls) -> "UpworkService":
        return cls(UpworkConfig.from_env())

    def resolve_access_token(self) -> str:
        if self._config.access_token:
            return self._config.access_token
        if self._config.client_id and self._config.client_secret and self._config.refresh_token:
            return self.refresh_access_token()
        if self._config.client_id and self._config.client_secret:
            return self.client_credentials_access_token()
        raise UpworkServiceError("Не удалось получить access token для Upwork API.")

    def refresh_access_token(self) -> str:
        if not (self._config.client_id and self._config.client_secret and self._config.refresh_token):
            raise UpworkServiceError("Для refresh token flow нужны UPWORK_CLIENT_ID, UPWORK_CLIENT_SECRET, UPWORK_REFRESH_TOKEN.")
        payload = parse.urlencode(
            {
                "grant_type": "refresh_token",
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                "refresh_token": self._config.refresh_token,
            }
        ).encode("utf-8")
        response_payload = self._post_form(UPWORK_OAUTH_TOKEN_URL, payload)
        access_token = str(response_payload.get("access_token", "")).strip()
        if not access_token:
            raise UpworkServiceError("Upwork OAuth refresh token flow не вернул access_token.")
        return access_token

    def client_credentials_access_token(self) -> str:
        if not (self._config.client_id and self._config.client_secret):
            raise UpworkServiceError("Для client credentials flow нужны UPWORK_CLIENT_ID и UPWORK_CLIENT_SECRET.")
        payload = parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
            }
        ).encode("utf-8")
        response_payload = self._post_form(UPWORK_OAUTH_TOKEN_URL, payload)
        access_token = str(response_payload.get("access_token", "")).strip()
        if not access_token:
            raise UpworkServiceError("Upwork OAuth client credentials flow не вернул access_token.")
        return access_token

    def build_public_job_search_query(self) -> str:
        return """
query publicMarketplaceJobPostingsSearch($marketPlaceJobFilter: PublicMarketplaceJobPostingsSearchFilter!) {
  publicMarketplaceJobPostingsSearch(marketPlaceJobFilter: $marketPlaceJobFilter) {
    jobs {
      recno
      ciphertext
      title
      description
      createdDateTime
      jobStatus
      contractorTier
      type
      engagement
      skills {
        name
        prettyName
      }
    }
  }
}
""".strip()

    def collect_marketplace_jobs(
        self,
        *,
        search_query: str = DEFAULT_SEARCH_QUERY,
        limit: int = 100,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        if limit < 1:
            raise UpworkServiceError("limit должен быть больше 0.")
        if page_size < 1:
            raise UpworkServiceError("page_size должен быть больше 0.")

        token = self.resolve_access_token()
        collected: list[dict[str, Any]] = []
        offset = 0
        query = self.build_public_job_search_query()

        while len(collected) < limit:
            rows = min(page_size, limit - len(collected))
            variables = {
                "marketPlaceJobFilter": {
                    "searchExpression_eq": search_query,
                    "pagination_eq": {"start": offset, "rows": rows},
                }
            }
            response_payload = self._post_graphql(query=query, variables=variables, access_token=token)
            jobs = _extract_public_search_jobs(response_payload)
            if not jobs:
                break
            normalized_jobs = [self._normalize_public_job(job) for job in jobs]
            collected.extend(normalized_jobs)
            offset += rows
            if len(jobs) < rows:
                break

        return {
            "source": "upwork",
            "query": search_query,
            "count": len(collected),
            "items": collected[:limit],
        }

    def _normalize_public_job(self, item: dict[str, Any]) -> dict[str, Any]:
        skills = []
        skills_raw = item.get("skills", [])
        if isinstance(skills_raw, list):
            for skill in skills_raw:
                if not isinstance(skill, dict):
                    continue
                skill_name = str(skill.get("prettyName") or skill.get("name") or "").strip()
                if skill_name:
                    skills.append(skill_name)

        ciphertext = str(item.get("ciphertext", "")).strip()
        title = str(item.get("title", "")).strip()
        description = str(item.get("description", "")).strip()
        published_at = str(item.get("createdDateTime", "")).strip()
        uid = ciphertext or str(item.get("recno", "")).strip()
        external_link = f"https://www.upwork.com/jobs/~{ciphertext}" if ciphertext else ""

        return {
            "uid": uid,
            "externalLink": external_link,
            "title": title,
            "description": description,
            "publishedAt": published_at,
            "skills": skills,
            "jobStatus": str(item.get("jobStatus", "")).strip(),
            "contractorTier": str(item.get("contractorTier", "")).strip(),
            "contractType": str(item.get("type", "")).strip(),
            "engagement": str(item.get("engagement", "")).strip(),
        }

    def _post_graphql(
        self,
        *,
        query: str,
        variables: dict[str, Any],
        access_token: str,
    ) -> dict[str, Any]:
        payload = json.dumps({"query": query, "variables": variables}, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            UPWORK_GRAPHQL_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        return self._send_json_request(req, "Upwork GraphQL API")

    def _post_form(self, url: str, payload: bytes) -> dict[str, Any]:
        req = request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        return self._send_json_request(req, "Upwork OAuth API")

    def _send_json_request(self, req: request.Request, label: str) -> dict[str, Any]:
        try:
            with request.urlopen(req, timeout=180) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise UpworkServiceError(f"{label} вернул {exc.code}: {body}") from exc
        except error.URLError as exc:
            raise UpworkServiceError(f"Не удалось подключиться к {label}: {exc.reason}") from exc

        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise UpworkServiceError(f"{label} вернул невалидный JSON.") from exc
        if not isinstance(data, dict):
            raise UpworkServiceError(f"{label} вернул неожиданный формат ответа.")
        errors_payload = data.get("errors")
        if isinstance(errors_payload, list) and errors_payload:
            message = "; ".join(str(item.get("message", "")).strip() for item in errors_payload if isinstance(item, dict))
            raise UpworkServiceError(message or f"{label} вернул GraphQL errors.")
        return data


def _extract_public_search_jobs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data", {})
    if not isinstance(data, dict):
        return []
    search_result = data.get("publicMarketplaceJobPostingsSearch", {})
    if not isinstance(search_result, dict):
        return []
    jobs = search_result.get("jobs", [])
    if not isinstance(jobs, list):
        return []
    return [item for item in jobs if isinstance(item, dict)]
