"""Webshare API client for proxy usage snapshots.

This module fetches usage data from Webshare and normalizes it into
numeric counters suitable for DB storage and Grafana charts.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)


@dataclass(slots=True)
class ProxyUsageSnapshot:
    """Normalized proxy usage metrics extracted from Webshare payload."""

    requests_used: int | None
    bytes_used: int | None
    bytes_remaining: int | None
    bytes_limit: int | None
    endpoint: str
    raw_payload: dict[str, Any]


class WebshareClient:
    """Minimal Webshare API client used by scraper container."""

    def __init__(self, api_key: str, timeout_sec: int = 20) -> None:
        self.api_key = api_key
        self.timeout_sec = timeout_sec
        self.base_url = "https://proxy.webshare.io"

    def fetch_usage_snapshot(self) -> ProxyUsageSnapshot:
        """Fetch usage metrics from Webshare API.

        Tries a small set of known endpoints because response contracts can
        differ across account plans/API versions.
        """
        # Primary source of real traffic usage in Webshare API.
        plan_id = self._fetch_plan_id()
        primary = f"/api/v2/stats/aggregate/?plan_id={plan_id}"
        endpoints = [
            primary,
            f"/api/v2/stats/?plan_id={plan_id}&page=1&page_size=1",
        ]

        last_error: Exception | None = None
        for endpoint in endpoints:
            try:
                payload_raw = self._get_json(endpoint)
                payload = self._coerce_payload(payload_raw)
                snapshot = self._normalize_payload(payload, endpoint)
                if (
                    snapshot.bytes_used is not None
                    or snapshot.requests_used is not None
                ):
                    return snapshot
                log.warning(
                    "Webshare endpoint %s responded but no usage counters found.",
                    endpoint,
                )
            except Exception as exc:  # pragma: no cover (network dependent)
                last_error = exc
                log.warning("Webshare endpoint %s failed: %s", endpoint, exc)

        if last_error is not None:
            raise RuntimeError(
                f"Could not fetch Webshare usage metrics: {last_error}"
            ) from last_error

        raise RuntimeError("Webshare responded, but usage metrics were missing")

    def _fetch_plan_id(self) -> int:
        payload = self._get_json("/api/v2/subscription/")
        plan_id = payload.get("plan")
        if not isinstance(plan_id, int):
            parsed = self._parse_numeric(plan_id)
            if parsed is None:
                raise RuntimeError("Webshare subscription payload has no plan id")
            return parsed
        return plan_id

    def _get_json(self, endpoint: str) -> Any:
        url = f"{self.base_url}{endpoint}"
        req = Request(
            url,
            headers={
                "Authorization": f"Token {self.api_key}",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with urlopen(req, timeout=self.timeout_sec) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                data = json.loads(body)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {body[:300]}") from exc
        except URLError as exc:
            raise RuntimeError(f"Network error: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON from Webshare: {exc}") from exc

        return data

    @staticmethod
    def _coerce_payload(payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            return payload[0]
        raise RuntimeError("Unexpected Webshare payload type")

    def _normalize_payload(
        self,
        payload: dict[str, Any],
        endpoint: str,
    ) -> ProxyUsageSnapshot:
        requests_used = self._extract_first_int(
            payload,
            [
                "request_count",
                "requests_count",
                "requests_used",
                "total_requests",
                "requests",
            ],
        )
        bytes_used = self._extract_first_int(
            payload,
            [
                "bytes_used",
                "used_bytes",
                "bandwidth_total",
                "traffic_used",
                "bandwidth_used",
                "usage_bytes",
            ],
        )
        bytes_remaining = self._extract_first_int(
            payload,
            [
                "bytes_remaining",
                "remaining_bytes",
                "traffic_remaining",
                "bandwidth_remaining",
            ],
        )
        bytes_limit = self._extract_first_int(
            payload,
            [
                "bytes_limit",
                "limit_bytes",
                "bandwidth_projected",
                "traffic_limit",
                "bandwidth_limit",
                "monthly_traffic_limit",
            ],
        )

        if requests_used is None:
            requests_used = self._extract_first_int(
                payload,
                [
                    "requests_total",
                    "requests_successful",
                ],
            )

        return ProxyUsageSnapshot(
            requests_used=requests_used,
            bytes_used=bytes_used,
            bytes_remaining=bytes_remaining,
            bytes_limit=bytes_limit,
            endpoint=endpoint,
            raw_payload=payload,
        )

    @classmethod
    def _extract_first_int(
        cls,
        obj: Any,
        candidate_keys: list[str],
    ) -> int | None:
        flattened = cls._flatten(obj)
        for raw_key, value in flattened.items():
            key = raw_key.lower()
            if any(c in key for c in candidate_keys):
                parsed = cls._parse_numeric(value)
                if parsed is not None:
                    return parsed
        return None

    @classmethod
    def _flatten(
        cls,
        obj: Any,
        prefix: str = "",
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = f"{prefix}.{k}" if prefix else str(k)
                out.update(cls._flatten(v, key))
        elif isinstance(obj, list):
            for idx, v in enumerate(obj):
                key = f"{prefix}[{idx}]"
                out.update(cls._flatten(v, key))
        else:
            out[prefix] = obj
        return out

    @staticmethod
    def _parse_numeric(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            cleaned = value.strip().replace(",", "")
            m = re.search(r"-?\d+(?:\.\d+)?", cleaned)
            if not m:
                return None
            try:
                return int(float(m.group(0)))
            except ValueError:
                return None
        return None

