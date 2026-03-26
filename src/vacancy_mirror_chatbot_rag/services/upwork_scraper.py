"""Upwork vacancy scraper service.

Loads Upwork search pages iteratively and extracts vacancy data from
the ``window.__NUXT__.state.jobsSearch`` object embedded in each SSR
HTML page.  No internal API calls needed — the full job list is already
present in the page HTML on every load.

Features:
- Retry logic per page (up to ``max_retries`` attempts).
- Cloudflare block detection — pauses and asks user to solve manually.
- Checkpoint save after every page so progress survives crashes.
- Resume from last saved checkpoint on restart.

Usage example::

    scraper = UpworkScraperService()
    await scraper.start_browser()
    await scraper.manual_cloudflare_pass(
        "https://www.upwork.com/nx/search/jobs/"
        "?category2_uid=531770282580668418&per_page=50&page=1"
    )
    jobs = await scraper.scrape_category(
        category_uid="531770282580668418",
        max_pages=100,
    )
    await scraper.stop_browser()
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from pathlib import Path
from typing import Any

import nodriver as uc

log = logging.getLogger(__name__)

CHROME_PATH = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)
SEARCH_BASE = "https://www.upwork.com/nx/search/jobs/"
PER_PAGE = 50
# Upwork only serves up to page 100 (5 000 jobs per category)
MAX_ALLOWED_PAGE = 100

# Strings that indicate Cloudflare challenge page
_CF_INDICATORS: tuple[str, ...] = (
    "challenges.cloudflare.com",
    "cf-browser-verification",
    "cf_clearance",
    "Just a moment",
    "Enable JavaScript and cookies to continue",
)


def _build_url(
    category_uid: str,
    page: int,
    extra_params: dict[str, str] | None = None,
) -> str:
    """Build a category search URL for a given page number.

    Args:
        category_uid: The Upwork ``category2_uid`` value.
        page: 1-based page number.
        extra_params: Optional additional query parameters (for future
            filter-based splitting, e.g. hourly rate ranges).

    Returns:
        Full Upwork search URL string.
    """
    url = (
        f"{SEARCH_BASE}"
        f"?category2_uid={category_uid}"
        f"&per_page={PER_PAGE}"
        f"&page={page}"
    )
    if extra_params:
        for key, value in extra_params.items():
            url += f"&{key}={value}"
    return url


def _extract_jobs(nuxt: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull the jobs list out of the window.__NUXT__ payload."""
    return (
        nuxt
        .get("state", {})
        .get("jobsSearch", {})
        .get("jobs", [])
    )


def _extract_paging(nuxt: dict[str, Any]) -> dict[str, int]:
    """Pull paging metadata out of the window.__NUXT__ payload."""
    return (
        nuxt
        .get("state", {})
        .get("jobsSearch", {})
        .get("paging", {})
    )


def _is_cloudflare_block(html: str) -> bool:
    """Return True if the page HTML looks like a Cloudflare challenge."""
    return any(indicator in html for indicator in _CF_INDICATORS)


class ScraperError(Exception):
    """Raised when scraping fails after all retries."""


class UpworkScraperService:
    """Browser-based Upwork vacancy scraper.

    Uses nodriver (real Chrome) to load SSR search pages and extract
    job listings from ``window.__NUXT__.state.jobsSearch``.

    Attributes:
        browser: The nodriver browser instance (set after start).
        page: The active tab (set after start).
    """

    def __init__(
        self,
        chrome_path: str = CHROME_PATH,
        page_delay_min: float = 10.0,
        page_delay_max: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 10.0,
        checkpoint_dir: Path | None = None,
    ) -> None:
        """Initialise the scraper.

        Args:
            chrome_path: Absolute path to the Chrome executable.
            page_delay_min: Minimum seconds to wait between page loads.
            page_delay_max: Maximum seconds to wait between page loads.
                Actual delay is sampled uniformly from
                ``[page_delay_min, page_delay_max]`` on every request,
                making the timing pattern unpredictable to rate-limiters.
            max_retries: How many times to retry a failed page before
                giving up or asking the user to intervene.
            retry_delay: Seconds to wait between retries.
            checkpoint_dir: Directory to save per-page checkpoint JSON
                files.  Defaults to ``data/checkpoints/``.
        """
        if page_delay_min > page_delay_max:
            raise ValueError(
                f"page_delay_min ({page_delay_min}) must be "
                f"<= page_delay_max ({page_delay_max})"
            )
        self.chrome_path = chrome_path
        self.page_delay_min = page_delay_min
        self.page_delay_max = page_delay_max
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.checkpoint_dir = checkpoint_dir or Path("data/checkpoints")
        self.browser: uc.Browser | None = None
        self.page: uc.Tab | None = None

    def _random_delay(self) -> float:
        """Return a uniformly sampled delay from [min, max].

        Example: min=10, max=30 → sleep between 10 s and 30 s.
        """
        return random.uniform(self.page_delay_min, self.page_delay_max)

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    async def start_browser(self) -> None:
        """Launch Chrome and open a blank tab."""
        self.browser = await uc.start(
            browser_executable_path=self.chrome_path
        )
        self.page = await self.browser.get("about:blank")
        log.info("Browser started.")

    async def stop_browser(self) -> None:
        """Close the browser gracefully."""
        if self.browser:
            self.browser.stop()
            self.browser = None
            self.page = None
            log.info("Browser stopped.")

    async def manual_cloudflare_pass(self, first_url: str) -> None:
        """Open the first URL and wait for the user to pass Cloudflare.

        Args:
            first_url: The URL to navigate to initially.
        """
        if self.page is None:
            raise RuntimeError(
                "Browser not started. Call start_browser() first."
            )
        log.info("Opening: %s", first_url)
        await self.page.get(first_url)
        input(
            ">>> Pass Cloudflare / cookie banner if needed, "
            "then press Enter: "
        )
        await self._dismiss_cookie_banner()

    async def _dismiss_cookie_banner(self) -> None:
        """Click the OneTrust cookie banner if it appears."""
        assert self.page is not None
        for _ in range(10):
            btn = await self.page.find("#onetrust-accept-btn-handler")
            if btn:
                log.info("Dismissing cookie banner...")
                await btn.click()
                await asyncio.sleep(2)
                return
            await asyncio.sleep(1)

    # ------------------------------------------------------------------
    # Checkpoint helpers
    # ------------------------------------------------------------------

    def _checkpoint_path(
        self, category_uid: str, page_num: int
    ) -> Path:
        """Return the checkpoint file path for a given page."""
        return (
            self.checkpoint_dir
            / category_uid
            / f"page_{page_num:04d}.json"
        )

    def _save_checkpoint(
        self,
        category_uid: str,
        page_num: int,
        jobs: list[dict[str, Any]],
    ) -> None:
        """Save a single page's jobs to a checkpoint file.

        Args:
            category_uid: The category UID being scraped.
            page_num: The page number just fetched.
            jobs: List of job dicts from that page.
        """
        path = self._checkpoint_path(category_uid, page_num)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(jobs, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load_checkpoint(
        self, category_uid: str, page_num: int
    ) -> list[dict[str, Any]] | None:
        """Load a checkpoint file if it exists.

        Returns:
            List of job dicts, or None if checkpoint does not exist.
        """
        path = self._checkpoint_path(category_uid, page_num)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Corrupt checkpoint %s: %s", path, exc)
            return None

    def _first_missing_page(
        self, category_uid: str, max_pages: int, start_page: int
    ) -> int:
        """Return the first page number that has no checkpoint yet.

        Used to resume an interrupted run.

        Args:
            category_uid: The category UID.
            max_pages: Maximum pages planned.
            start_page: The start page number.

        Returns:
            Page number to resume from.
        """
        for p in range(start_page, start_page + max_pages):
            if self._load_checkpoint(category_uid, p) is None:
                return p
        return start_page + max_pages  # all done

    def load_all_checkpoints(
        self,
        category_uid: str,
        start_page: int,
        end_page: int,
    ) -> list[dict[str, Any]]:
        """Merge all checkpoint files for a category into one list.

        Args:
            category_uid: The category UID.
            start_page: First page number (inclusive).
            end_page: Last page number (inclusive).

        Returns:
            Flat list of all job dicts across all checkpoint pages.
        """
        all_jobs: list[dict[str, Any]] = []
        for p in range(start_page, end_page + 1):
            jobs = self._load_checkpoint(category_uid, p)
            if jobs is not None:
                all_jobs.extend(jobs)
        return all_jobs

    # ------------------------------------------------------------------
    # Core page loading
    # ------------------------------------------------------------------

    async def _get_page_html(self) -> str:
        """Return the current page's outer HTML."""
        assert self.page is not None
        return await self.page.evaluate(
            "document.documentElement.outerHTML"
        )

    async def _get_nuxt(self) -> dict[str, Any] | None:
        """Extract window.__NUXT__ from the current page.

        Returns:
            Parsed dict, or None if unavailable.
        """
        assert self.page is not None
        raw: str = await self.page.evaluate(
            "JSON.stringify(window.__NUXT__ || null)"
        )
        if not raw or raw == "null":
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            log.error("JSON parse error in __NUXT__: %s", exc)
            return None

    async def _load_page_with_retry(
        self,
        url: str,
        page_num: int,
    ) -> list[dict[str, Any]] | None:
        """Load a single page, retrying on failure.

        Detects Cloudflare challenges and pauses for manual resolution.

        Args:
            url: Full Upwork search URL.
            page_num: Page number (for logging).

        Returns:
            List of job dicts, or None if all retries failed.
        """
        assert self.page is not None

        for attempt in range(1, self.max_retries + 1):
            log.debug(
                "Loading page %d (attempt %d/%d): %s",
                page_num, attempt, self.max_retries, url,
            )
            await self.page.get(url)
            delay = self._random_delay()
            log.debug("Waiting %.2fs after page load...", delay)
            await asyncio.sleep(delay)

            # Check for Cloudflare block
            html = await self._get_page_html()
            if _is_cloudflare_block(html):
                log.warning(
                    "Cloudflare block detected on page %d! "
                    "Please solve it in the browser.",
                    page_num,
                )
                input(
                    ">>> Solve Cloudflare in the browser, "
                    "then press Enter to retry: "
                )
                continue  # retry after manual solve

            nuxt = await self._get_nuxt()
            if nuxt is None:
                log.warning(
                    "No __NUXT__ on page %d (attempt %d/%d).",
                    page_num, attempt, self.max_retries,
                )
                if attempt < self.max_retries:
                    log.info(
                        "Retrying in %.1fs...", self.retry_delay
                    )
                    await asyncio.sleep(self.retry_delay)
                continue

            jobs = _extract_jobs(nuxt)
            if not jobs and attempt < self.max_retries:
                log.warning(
                    "Empty jobs on page %d (attempt %d/%d), retrying.",
                    page_num, attempt, self.max_retries,
                )
                await asyncio.sleep(self.retry_delay)
                continue

            return jobs

        log.error(
            "Page %d failed after %d attempts.", page_num, self.max_retries
        )
        return None

    # ------------------------------------------------------------------
    # Public scraping API
    # ------------------------------------------------------------------

    async def scrape_category(
        self,
        category_uid: str,
        *,
        max_pages: int = 50,
        start_page: int = 1,
        resume: bool = True,
        extra_params: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Scrape all vacancy pages for one category UID.

        Iterates pages from ``start_page`` until ``max_pages`` or until
        Upwork returns fewer jobs than ``PER_PAGE`` (last page reached).
        Saves a checkpoint after every successful page.  If ``resume``
        is True, skips pages that already have checkpoint files.

        Args:
            category_uid: The Upwork ``category2_uid`` string.
            max_pages: Maximum number of pages to fetch.
            start_page: Page to start from (1-based, default: 1).
            resume: If True, skip pages with existing checkpoints and
                continue from the first missing one.
            extra_params: Optional extra URL query params for filtering
                (e.g. ``{"hourly_rate": "10-30"}``).

        Returns:
            Flat list of raw job dicts from all fetched pages.
        """
        end_page = min(
            start_page + max_pages - 1, MAX_ALLOWED_PAGE
        )

        # Resume from last checkpoint if requested
        resume_from = start_page
        if resume:
            resume_from = self._first_missing_page(
                category_uid, max_pages, start_page
            )
            already_done = resume_from - start_page
            if already_done > 0:
                log.info(
                    "Resuming from page %d "
                    "(%d pages already checkpointed).",
                    resume_from, already_done,
                )

        total_reported: int | None = None

        for page_num in range(resume_from, end_page + 1):
            url = _build_url(category_uid, page_num, extra_params)
            jobs = await self._load_page_with_retry(url, page_num)

            if jobs is None:
                log.error(
                    "Stopping category %s at page %d due to errors.",
                    category_uid, page_num,
                )
                break

            # Read total from first successful page
            if total_reported is None:
                nuxt = await self._get_nuxt()
                if nuxt:
                    paging = _extract_paging(nuxt)
                    total_reported = paging.get("total", 0)
                    log.info(
                        "Category %s: %d total jobs on Upwork "
                        "(max fetchable: %d).",
                        category_uid,
                        total_reported,
                        MAX_ALLOWED_PAGE * PER_PAGE,
                    )

            # Save checkpoint immediately
            self._save_checkpoint(category_uid, page_num, jobs)

            fetched_so_far = (page_num - start_page + 1) * PER_PAGE
            log.info(
                "Page %3d/%d — %2d jobs fetched  "
                "(checkpoint saved, ~%d total so far)",
                page_num,
                end_page,
                len(jobs),
                fetched_so_far,
            )

            # Stop early if last page
            if len(jobs) < PER_PAGE:
                log.info(
                    "Last page reached at page %d "
                    "(%d jobs, less than %d).",
                    page_num, len(jobs), PER_PAGE,
                )
                end_page = page_num
                break

        # Merge all checkpoints into final result
        all_jobs = self.load_all_checkpoints(
            category_uid, start_page, end_page
        )
        log.info(
            "Category %s done: %d jobs total across pages %d–%d.",
            category_uid, len(all_jobs), start_page, end_page,
        )
        return all_jobs

    async def scrape_all_categories(
        self,
        category_uids: dict[str, str],
        *,
        max_pages_per_category: int = 50,
        output_dir: Path | None = None,
        resume: bool = True,
    ) -> dict[str, list[dict[str, Any]]]:
        """Scrape vacancies for multiple categories sequentially.

        Args:
            category_uids: Mapping of category name → category2_uid,
                e.g. from ``categories.CATEGORY_UIDS``.
            max_pages_per_category: Max pages to fetch per category.
            output_dir: If given, saves each category's merged jobs as
                a JSON file immediately after scraping.
            resume: If True, resume from existing checkpoints.

        Returns:
            Mapping of category name → list of job dicts.
        """
        results: dict[str, list[dict[str, Any]]] = {}

        for name, uid in category_uids.items():
            log.info(
                "=== Scraping: %s (uid=%s) ===", name, uid
            )
            jobs = await self.scrape_category(
                uid,
                max_pages=max_pages_per_category,
                resume=resume,
            )
            results[name] = jobs

            if output_dir is not None:
                output_dir.mkdir(parents=True, exist_ok=True)
                safe_name = (
                    name.lower()
                    .replace(" ", "_")
                    .replace("/", "_")
                    .replace("&", "and")
                    .replace(",", "")
                )
                out_path = output_dir / f"{safe_name}.json"
                out_path.write_text(
                    json.dumps(jobs, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                log.info(
                    "Saved %d jobs → %s", len(jobs), out_path
                )

        return results
