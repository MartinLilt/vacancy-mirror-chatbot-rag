"""Scrape Upwork category UIDs by clicking each category in the filter."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import nodriver as uc

CHROME_PATH = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)
OUTPUT_FILE = Path("scripts/upwork_category_uids.json")

SEARCH_BASE = (
    "https://www.upwork.com/nx/search/jobs/"
    "?q=web%20development&per_page=50"
)


def extract_uid_from_url(url: str) -> str | None:
    """Extract category2_uid query param from a URL string."""
    params = parse_qs(urlparse(url).query)
    uids = params.get("category2_uid")
    return uids[0] if uids else None


async def wait_for_categories_block(
    page: uc.Tab,
    timeout: int = 15,
) -> bool:
    """Poll until [filtername="categories"] appears in the DOM.

    Args:
        page: The nodriver tab instance.
        timeout: Maximum seconds to wait.

    Returns:
        True if the block appeared within timeout, False otherwise.
    """
    print(f"  → Waiting for categories block (up to {timeout}s)...")
    for _ in range(timeout):
        exists: bool = await page.evaluate(
            '!!document.querySelector(\'[filtername="categories"]\')'
        )
        if exists:
            print("  → Categories block is ready.")
            return True
        await asyncio.sleep(1)
    print("  → Timed out waiting for categories block!")
    return False


async def dismiss_cookie_banner(page: uc.Tab) -> None:
    """Click 'Accept All' on the OneTrust cookie banner if it appears.

    The banner may appear 5-7 seconds after page load, so we poll
    for up to 10 seconds before giving up silently.  After clicking,
    we wait for the categories filter block to re-appear in the DOM
    instead of using a fixed sleep.
    """
    print("Waiting for cookie banner (up to 10s)...")
    for attempt in range(10):
        btn = await page.find("#onetrust-accept-btn-handler")
        if btn:
            print(
                f"  → Cookie banner found (attempt {attempt + 1}),"
                " clicking Accept All..."
            )
            await btn.click()
            # DOM re-renders after banner — poll for categories block
            await wait_for_categories_block(page, timeout=15)
            print("  → Cookie banner dismissed.")
            return
        await asyncio.sleep(1)
    print("  → No cookie banner appeared, continuing.")


async def open_category_dropdown(page: uc.Tab) -> bool:
    """Ensure the category dropdown is open.

    Clicks the toggle only if it is currently closed.
    Returns True if dropdown is open after the call.
    """
    # Guarantee the categories block is present before doing anything
    block_ready = await wait_for_categories_block(page, timeout=15)
    if not block_ready:
        print("  → Categories block never appeared, aborting.")
        return False

    # Check current state first
    expanded: bool = await page.evaluate("""
        (function() {
            const block = document.querySelector(
                '[filtername="categories"]'
            );
            if (!block) return false;
            const toggle = block.querySelector(
                '[data-test="dropdown-toggle UpCDropdownToggle"]'
            );
            return toggle
                ? toggle.getAttribute('aria-expanded') === 'true'
                : false;
        })()
    """)
    if expanded:
        return True

    print("  → Dropdown closed, clicking to open...")
    clicked: bool = await page.evaluate("""
        (function() {
            const block = document.querySelector(
                '[filtername="categories"]'
            );
            if (!block) return false;
            const toggle = block.querySelector(
                '[data-test="dropdown-toggle UpCDropdownToggle"]'
            );
            if (!toggle) return false;
            toggle.click();
            return true;
        })()
    """)
    if not clicked:
        print("  → ERROR: toggle not found!")
        return False
    await asyncio.sleep(1.5)
    expanded = await page.evaluate("""
        (function() {
            const block = document.querySelector(
                '[filtername="categories"]'
            );
            if (!block) return false;
            const toggle = block.querySelector(
                '[data-test="dropdown-toggle UpCDropdownToggle"]'
            );
            return toggle
                ? toggle.getAttribute('aria-expanded') === 'true'
                : false;
        })()
    """)
    print(f"  → aria-expanded: {expanded}")
    return expanded


async def scrape_category_uids(page: uc.Tab) -> dict[str, str]:
    """Click each category option and collect its category2_uid from URL.

    Returns:
        Mapping of category label → category2_uid string.
    """
    uid_map: dict[str, str] = {}

    # Open dropdown FIRST, then read all labels
    opened = await open_category_dropdown(page)
    if not opened:
        print("  → Dropdown did not open, aborting.")
        return uid_map

    # Collect all labels while dropdown is open
    labels_raw: str = await page.evaluate("""
        (function() {
            const block = document.querySelector(
                '[filtername="categories"]'
            );
            if (!block) return '';
            return Array.from(block.querySelectorAll('li'))
                .map(el => el.innerText.trim())
                .filter(t => t.length > 0)
                .join('|||');
        })()
    """)
    labels: list[str] = [
        lbl for lbl in labels_raw.split("|||") if lbl.strip()
    ]
    total = len(labels)
    print(f"Found {total} category options: {labels[:5]}...")

    for i, label in enumerate(labels):
        # Re-open dropdown before each click
        opened = await open_category_dropdown(page)
        if not opened:
            print(f"  [{i}] Could not open dropdown, stopping.")
            break

        # Click item at index i via JS
        await page.evaluate(f"""
            (function() {{
                const block = document.querySelector(
                    '[filtername="categories"]'
                );
                if (!block) return;
                const items = block.querySelectorAll('li');
                if (items[{i}]) items[{i}].click();
            }})()
        """)
        await asyncio.sleep(1.2)

        # Extract category2_uid from the updated URL
        current_url: str = await page.evaluate(
            "window.location.href"
        )
        uid = extract_uid_from_url(current_url)

        if uid:
            uid_map[label] = uid
            print(f"  [{i+1}/{total}] {label!r:45s} → {uid}")
        else:
            print(f"  [{i+1}/{total}] {label!r:45s} → no uid")

    return uid_map


async def main() -> None:
    browser = await uc.start(browser_executable_path=CHROME_PATH)
    page = await browser.get("about:blank")

    print(f"Opening: {SEARCH_BASE}")
    await page.get(SEARCH_BASE)

    print("Pass Cloudflare if needed, then press Enter in terminal...")
    input(">>> Press Enter when Upwork jobs page is fully loaded: ")

    # Verify we are on the right page
    current_url: str = await page.evaluate("window.location.href")
    print(f"Current URL: {current_url}")
    title: str = await page.evaluate("document.title")
    print(f"Page title:  {title}")

    # Dismiss cookie consent banner if it appears
    await dismiss_cookie_banner(page)

    print("\nStarting category UID scraping...")
    uid_map = await scrape_category_uids(page)

    print(f"\nCollected {len(uid_map)} category UIDs")
    OUTPUT_FILE.write_text(json.dumps(uid_map, indent=2, ensure_ascii=False))
    print(f"Saved → {OUTPUT_FILE}")

    input("\nPress Enter to close the browser...")
    browser.stop()


if __name__ == "__main__":
    uc.loop().run_until_complete(main())
