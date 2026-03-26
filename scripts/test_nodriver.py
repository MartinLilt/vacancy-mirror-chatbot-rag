"""Test: open Upwork, pass Cloudflare manually, save cookies for reuse."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import nodriver as uc
from nodriver import cdp

CHROME_PATH = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)
COOKIES_FILE = Path("scripts/upwork_cookies.json")

# Allowed values for per_page parameter
PER_PAGE_OPTIONS: tuple[int, int, int] = (10, 20, 50)
# Default: maximum jobs per page
PER_PAGE_DEFAULT: int = 50
# Pagination range: pages 1..100
PAGE_MIN: int = 1
PAGE_MAX: int = 100

SEARCH_BASE = "https://www.upwork.com/nx/search/jobs/"


def build_search_url(
    query: str,
    *,
    page: int = PAGE_MIN,
    per_page: int = PER_PAGE_DEFAULT,
) -> str:
    """Build a paginated Upwork job search URL.

    Args:
        query: Search keyword or category (e.g. 'web development').
        page: Page number, must be between PAGE_MIN and PAGE_MAX.
        per_page: Jobs per page — one of PER_PAGE_OPTIONS (10, 20, 50).

    Returns:
        Full Upwork search URL string.
    """
    if per_page not in PER_PAGE_OPTIONS:
        raise ValueError(
            f"per_page must be one of {PER_PAGE_OPTIONS}, got {per_page}"
        )
    if not PAGE_MIN <= page <= PAGE_MAX:
        raise ValueError(
            f"page must be between {PAGE_MIN} and {PAGE_MAX}, got {page}"
        )
    encoded_query = query.replace(" ", "%20")
    return (
        f"{SEARCH_BASE}"
        f"?q={encoded_query}"
        f"&page={page}"
        f"&per_page={per_page}"
    )


async def load_cookies(page: uc.Tab) -> bool:
    """Load saved cookies if they exist. Returns True if loaded."""
    if not COOKIES_FILE.exists():
        return False
    cookies_data = json.loads(COOKIES_FILE.read_text())
    await page.send(cdp.storage.set_cookies(
        [cdp.network.CookieParam(**c) for c in cookies_data]
    ))
    print(f"Loaded {len(cookies_data)} cookies from {COOKIES_FILE}")
    return True


async def save_cookies(page: uc.Tab) -> None:
    """Save current browser cookies to file for reuse."""
    cookies = await page.browser.cookies.get_all()
    cookies_data = [c.__dict__ for c in cookies]
    COOKIES_FILE.write_text(json.dumps(cookies_data, indent=2))
    print(f"Saved {len(cookies_data)} cookies → {COOKIES_FILE}")


async def main() -> None:
    browser = await uc.start(browser_executable_path=CHROME_PATH)
    page = await browser.get("about:blank")

    # Enable network tracking
    await page.send(cdp.network.enable())

    # Try to restore previous session cookies
    has_cookies = await load_cookies(page)

    search_url = build_search_url("web development", page=1, per_page=50)
    print(f"Opening: {search_url}")
    await page.get(search_url)

    if has_cookies:
        print("Cookies found — waiting 5s (Cloudflare should not appear)...")
        await asyncio.sleep(5)
    else:
        print("No cookies found — please pass Cloudflare challenge manually!")
        print("Waiting 20s...")
        await asyncio.sleep(20)

    # Persist cookies for next run
    await save_cookies(page)

    title = await page.evaluate("document.title")
    print(f"\nPage title: {title}")

    url = await page.evaluate("window.location.href")
    print(f"Current URL: {url}")

    input("\nPress Enter to close the browser...")
    browser.stop()


if __name__ == "__main__":
    uc.loop().run_until_complete(main())
