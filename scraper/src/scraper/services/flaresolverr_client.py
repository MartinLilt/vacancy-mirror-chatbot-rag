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
        self, url: str, max_timeout: int = 60000, proxy: str | None = None
    ) -> dict[str, Any]:
        """
        Solve Cloudflare challenge for a given URL.

        Args:
            url: Target URL to solve
            max_timeout: Maximum timeout in milliseconds (default: 60s)
            proxy: Optional proxy URL (format: http://user:pass@host:port)

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

        logger.info(f"Requesting FlareSolverr to solve: {url}")
        logger.debug(f"Payload: {json.dumps(payload, indent=2)}")

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
