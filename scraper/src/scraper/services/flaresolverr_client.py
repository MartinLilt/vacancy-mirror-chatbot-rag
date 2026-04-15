"""FlareSolverr client for Cloudflare bypass."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse
from urllib import request
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)


class FlareSolverrClient:
    """Client for FlareSolverr API to bypass Cloudflare challenges."""

    def __init__(self, api_url: str = "http://localhost:8191/v1") -> None:
        """
        Initialize FlareSolverr client.

        Args:
            api_url: FlareSolverr API endpoint URL
        """
        self.api_url = api_url
        logger.info(f"FlareSolverr client initialized: {api_url}")

    @staticmethod
    def _build_proxy_payload(proxy: str) -> dict[str, str]:
        """Convert proxy URL to FlareSolverr proxy payload.

        FlareSolverr/Chromium is more reliable when credentials are passed as
        separate username/password fields instead of embedded in URL.
        """
        parsed = urlparse(proxy)
        if not parsed.scheme or not parsed.hostname or not parsed.port:
            raise ValueError(f"Invalid proxy URL: {proxy}")

        payload: dict[str, str] = {
            "url": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
        }
        if parsed.username:
            payload["username"] = parsed.username
        if parsed.password:
            payload["password"] = parsed.password
        return payload

    def solve(
        self,
        url: str,
        max_timeout: int = 60000,
        proxy: str | None = None,
        session: str | None = None,
    ) -> dict[str, Any]:
        """
        Solve Cloudflare challenge for a given URL.

        Args:
            url: Target URL to solve
            max_timeout: Maximum timeout in milliseconds (default: 60s)
            proxy: Optional proxy URL (format: http://user:pass@host:port)
            session: Optional FlareSolverr session id for sticky reuse

        Returns:
            Dict with 'cookies', 'userAgent', and 'html' keys

        Raises:
            RuntimeError: If FlareSolverr request fails
        """
        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": max_timeout,
        }

        if proxy:
            payload["proxy"] = self._build_proxy_payload(proxy)
        if session:
            payload["session"] = session

        logger.info(f"Requesting FlareSolverr to solve: {url}")
        # Redact proxy credentials from debug logs
        if logger.isEnabledFor(logging.DEBUG):
            safe_payload = dict(payload)
            if "proxy" in safe_payload:
                safe_proxy = dict(safe_payload["proxy"])
                if "username" in safe_proxy:
                    safe_proxy["username"] = "***"
                if "password" in safe_proxy:
                    safe_proxy["password"] = "***"
                safe_payload["proxy"] = safe_proxy
            logger.debug(f"Payload: {json.dumps(safe_payload, indent=2)}")

        try:
            req = request.Request(
                self.api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            timeout_seconds = max_timeout / 1000 + 10
            with request.urlopen(req, timeout=timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))

            if result.get("status") != "ok":
                error_msg = result.get("message", "Unknown error")
                raise RuntimeError(
                    f"FlareSolverr failed: {error_msg}"
                )

            solution = result.get("solution", {})
            cookies = solution.get("cookies", [])
            user_agent = solution.get("userAgent", "")
            html = solution.get("response", "")

            logger.info(
                f"✅ FlareSolverr solved! Cookies: {len(cookies)}, "
                f"UserAgent: {user_agent[:50]}..."
            )
            logger.info(f"HTML length: {len(html)} bytes")
            logger.debug(f"HTML preview: {html[:500]}...")

            return {
                "cookies": cookies,
                "userAgent": user_agent,
                "html": html,
            }

        except HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else "No details"
            raise RuntimeError(
                f"FlareSolverr HTTP error {e.code}: {error_body}"
            ) from e

        except URLError as e:
            raise RuntimeError(
                f"FlareSolverr connection error: {e.reason}"
            ) from e

        except Exception as e:
            raise RuntimeError(
                f"FlareSolverr unexpected error: {e}"
            ) from e

    def create_session(self, session_id: str) -> str:
        """Create a FlareSolverr browser session and return its id."""
        payload = {
            "cmd": "sessions.create",
            "session": session_id,
        }
        logger.info("Creating FlareSolverr session: %s", session_id)
        try:
            req = request.Request(
                self.api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("status") != "ok":
                raise RuntimeError(
                    f"FlareSolverr failed to create session: {result.get('message', 'Unknown error')}"
                )
            session = result.get("session") or session_id
            logger.info("FlareSolverr session ready: %s", session)
            return str(session)
        except Exception as e:
            raise RuntimeError(f"FlareSolverr create_session error: {e}") from e

    def destroy_session(self, session_id: str) -> None:
        """Destroy a FlareSolverr browser session."""
        payload = {
            "cmd": "sessions.destroy",
            "session": session_id,
        }
        logger.info("Destroying FlareSolverr session: %s", session_id)
        try:
            req = request.Request(
                self.api_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("status") != "ok":
                logger.warning(
                    "FlareSolverr could not destroy session %s: %s",
                    session_id,
                    result.get("message", "Unknown error"),
                )
        except Exception as e:
            logger.warning("FlareSolverr destroy_session error for %s: %s", session_id, e)

