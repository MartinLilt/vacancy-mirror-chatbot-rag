"""HTTP inference server for assistant replicas."""

from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from backend.services.openai import OpenAIMarketAssistantService
from backend.services.reasoning_orchestrator import ReasoningOrchestrator

log = logging.getLogger(__name__)


class AssistantInferServer:
    """Serve assistant answers over HTTP for horizontal replica scaling."""

    def __init__(
        self,
        *,
        host: str = "0.0.0.0",
        port: int | None = None,
    ) -> None:
        self.host = host
        self.port = port or int(os.environ.get("ASSISTANT_INFER_PORT", "8090"))
        self.max_concurrency = int(
            os.environ.get("ASSISTANT_INFER_MAX_CONCURRENCY", "24")
        )
        self.assistant = OpenAIMarketAssistantService()
        self.orchestrator_enabled = (
            os.environ.get("ASSISTANT_ORCHESTRATOR_ENABLED", "1").strip().lower()
            not in {"0", "false", "no", "off"}
        )
        self.orchestrator: ReasoningOrchestrator | None = None
        if self.orchestrator_enabled:
            self.orchestrator = ReasoningOrchestrator(llm=self.assistant)
        self._semaphore = threading.BoundedSemaphore(max(1, self.max_concurrency))

    def run(self) -> None:
        """Start blocking HTTP server."""
        server_ref = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
                log.debug(fmt, *args)

            def _json(self, status: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/health":
                    self._json(200, {"ok": True})
                    return
                self._json(404, {"ok": False, "error": "not_found"})

            def do_POST(self) -> None:  # noqa: N802
                if self.path != "/v1/answer":
                    self._json(404, {"ok": False, "error": "not_found"})
                    return

                if not server_ref._semaphore.acquire(blocking=False):
                    self._json(429, {"ok": False, "error": "overloaded"})
                    return

                try:
                    content_len = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(content_len)
                    payload = json.loads(raw.decode("utf-8"))
                    if not isinstance(payload, dict):
                        self._json(400, {"ok": False, "error": "invalid_payload"})
                        return

                    question = str(payload.get("question", "")).strip()
                    if not question:
                        self._json(400, {"ok": False, "error": "question_required"})
                        return

                    history_raw = payload.get("history", [])
                    history: list[dict[str, str]] = []
                    if isinstance(history_raw, list):
                        for item in history_raw[-8:]:
                            if not isinstance(item, dict):
                                continue
                            role = str(item.get("role", "user")).strip().lower()
                            if role not in {"user", "assistant"}:
                                role = "user"
                            content = str(item.get("content", "")).strip()
                            if not content:
                                continue
                            history.append({"role": role, "content": content})

                    route = "simple"
                    if server_ref.orchestrator is not None:
                        result = server_ref.orchestrator.run(
                            question=question,
                            history=history,
                        )
                        answer = result.final_answer
                        route = result.route
                    else:
                        answer = server_ref.assistant.answer_market_question(
                            question=question,
                        )

                    self._json(200, {
                        "ok": True,
                        "answer": answer,
                        "route": route,
                    })
                except Exception as exc:  # noqa: BLE001
                    self._json(500, {"ok": False, "error": str(exc)})
                finally:
                    server_ref._semaphore.release()

        server = ThreadingHTTPServer((self.host, self.port), _Handler)
        log.info(
            "Assistant infer server listening on %s:%s (max_concurrency=%s)",
            self.host,
            self.port,
            self.max_concurrency,
        )
        server.serve_forever()

