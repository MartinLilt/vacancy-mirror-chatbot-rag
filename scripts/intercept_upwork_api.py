"""Intercept Upwork internal API responses via CDP Network events.

Run this script once to identify which network request carries
vacancy JSON data.  All JSON responses >= 1 KB are saved to
``scripts/intercepted/`` for inspection.

Usage:
    python scripts/intercept_upwork_api.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path

import nodriver as uc
from nodriver import cdp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)

CHROME_PATH = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)
OUTPUT_DIR = Path("scripts/intercepted")

# One category URL to test — Web Dev category
TEST_URL = (
    "https://www.upwork.com/nx/search/jobs/"
    "?category2_uid=531770282580668418&per_page=50&page=1"
)

# Minimum response body size to save (bytes)
MIN_BODY_SIZE = 1024


async def enable_network(page: uc.Tab) -> None:
    """Enable CDP Network domain to receive response events."""
    await page.send(cdp.network.enable())


async def get_response_body(
    page: uc.Tab,
    request_id: cdp.network.RequestId,
) -> bytes | None:
    """Fetch the response body for a completed request.

    Returns raw bytes, or None if body is unavailable.
    """
    try:
        result = await page.send(
            cdp.network.get_response_body(request_id)
        )
        body_str: str = result[0]
        is_base64: bool = result[1]
        if is_base64:
            return base64.b64decode(body_str)
        return body_str.encode("utf-8")
    except Exception:
        return None


async def intercept(page: uc.Tab) -> None:
    """Listen for network responses and save JSON ones to disk."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    saved: int = 0
    # Track completed responses: request_id → url
    completed: dict[str, str] = {}

    def on_response(event: cdp.network.ResponseReceived) -> None:
        url: str = event.response.url
        mime: str = event.response.mime_type or ""
        # Only capture JSON responses
        if "json" not in mime and "javascript" not in mime:
            return
        completed[event.request_id] = url

    page.add_handler(cdp.network.ResponseReceived, on_response)

    log.info("Navigating to: %s", TEST_URL)
    await page.get(TEST_URL)

    log.info(
        "Pass Cloudflare if needed, then press Enter in terminal..."
    )
    input(">>> Press Enter when the page is fully loaded: ")

    # Dismiss cookie banner if present
    for _ in range(10):
        btn = await page.find("#onetrust-accept-btn-handler")
        if btn:
            log.info("Dismissing cookie banner...")
            await btn.click()
            await asyncio.sleep(2)
            break
        await asyncio.sleep(1)

    # Wait a bit more for any lazy-loaded requests
    log.info("Waiting 3s for network activity to settle...")
    await asyncio.sleep(3)

    log.info("Fetching bodies for %d captured responses...", len(completed))

    for req_id, url in completed.items():
        body = await get_response_body(page, req_id)
        if not body or len(body) < MIN_BODY_SIZE:
            continue

        # Try to parse as JSON
        try:
            parsed = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        # Build a safe filename from the URL
        safe_name = (
            url.split("?")[0]           # strip query params
            .replace("https://", "")
            .replace("http://", "")
            .replace("/", "__")
            .strip("_")[:120]           # max filename length
        )
        out_path = OUTPUT_DIR / f"{safe_name}.json"
        out_path.write_text(
            json.dumps(parsed, indent=2, ensure_ascii=False)
        )
        log.info(
            "Saved %6d bytes  →  %s", len(body), out_path.name
        )
        saved += 1

    log.info("Done. Saved %d JSON responses to %s/", saved, OUTPUT_DIR)
    input("\nPress Enter to close the browser...")


async def main() -> None:
    """Entry point."""
    browser = await uc.start(browser_executable_path=CHROME_PATH)
    page = await browser.get("about:blank")
    await enable_network(page)
    try:
        await intercept(page)
    finally:
        browser.stop()


if __name__ == "__main__":
    uc.loop().run_until_complete(main())
