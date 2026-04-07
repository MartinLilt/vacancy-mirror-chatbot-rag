"""HTTP client for calling assistant inference replicas."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any
from urllib import error, request


@dataclass
class AssistantInferClient:
    """Round-robin client over one or more assistant inference endpoints."""

    base_urls: list[str]
    _index: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def from_raw_urls(cls, raw_urls: str) -> "AssistantInferClient | None":
        urls = [u.strip().rstrip("/") for u in raw_urls.split(",") if u.strip()]
        if not urls:
            return None
        return cls(base_urls=urls)

    def _next_urls(self) -> list[str]:
        with self._lock:
            start = self._index
            self._index = (self._index + 1) % len(self.base_urls)
        ordered = self.base_urls[start:] + self.base_urls[:start]
        return ordered

    def generate_answer(
        self,
        *,
        question: str,
        history: list[dict[str, str]] | None = None,
        timeout_sec: float = 70.0,
    ) -> tuple[str, str]:
        """Request answer from replicas, cascading on failures."""
        payload = {
            "question": question,
            "history": history or [],
        }
        body = json.dumps(payload).encode("utf-8")
        last_error: Exception | None = None
        for base_url in self._next_urls():
            req = request.Request(
                url=f"{base_url}/v1/answer",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with request.urlopen(req, timeout=timeout_sec) as resp:
                    response_body = resp.read().decode("utf-8")
                    parsed: dict[str, Any] = json.loads(response_body)
                    answer = str(parsed.get("answer", "")).strip()
                    if not answer:
                        raise RuntimeError("Remote infer returned empty answer")
                    route = str(parsed.get("route", "simple")).strip() or "simple"
                    return answer, route
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
        raise RuntimeError(f"All assistant infer replicas failed: {last_error}")

