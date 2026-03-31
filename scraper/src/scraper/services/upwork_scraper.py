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

Classes:
- ``UpworkScraperService`` — scrapes job listings by category UID.
- ``CategoryScraperService`` — discovers all category UIDs and their
  total job counts by interacting with the Upwork search filter UI.

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

    # Discover categories:
    cat_scraper = CategoryScraperService()
    await cat_scraper.start_browser()
    await cat_scraper.manual_cloudflare_pass()
    categories = await cat_scraper.scrape_categories()
    await cat_scraper.stop_browser()
    # categories == {
    #   "Web, Mobile & Software Dev": {
    #       "uid": "531770282580668418",
    #       "total_jobs": 48320,
    #   },
    #   ...
    # }
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from pathlib import Path
from typing import Any

import nodriver as uc

from scraper.categories import classify_load

log = logging.getLogger(__name__)

# Read Chrome/Chromium path from env so the container can override it.
# Default falls back to macOS Chrome for local development.
CHROME_PATH: str = __import__("os").environ.get(
    "CHROME_PATH",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
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
        user_data_dir: Path | None = None,
        proxy_url: str | None = None,
        cookie_backup_path: Path | None = None,
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
            user_data_dir: Chrome User Data Directory for session
                persistence (cookies, localStorage, etc.).  If None,
                Chrome runs in ephemeral mode.
            proxy_url: Residential proxy URL with sticky session support.
                Format: ``http://user:pass@proxy.com:port``.  If None,
                uses server's direct IP.  Recommended: IPRoyal residential
                proxy with 24-hour session rotation.
            cookie_backup_path: Path to save/load cookies as JSON backup
                for disaster recovery.  Defaults to
                ``data/session_cookies.json``.
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
        self.user_data_dir = user_data_dir
        self.proxy_url = proxy_url
        self.cookie_backup_path = (
            cookie_backup_path or Path("data/session_cookies.json")
        )
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

    async def _apply_stealth_patches(self) -> None:
        """Remove webdriver flags and add realistic browser fingerprint.

        Executes CDP commands to:
        - Hide ``navigator.webdriver`` flag.
        - Add fake plugins (Chrome PDF Viewer, etc.).
        - Add fake languages (en-US, en).
        - Override user agent to look like real Chrome.

        Must be called AFTER browser starts but BEFORE loading any pages.
        """
        assert self.page is not None
        log.debug("Applying stealth patches...")

        cdp_page = __import__("nodriver.cdp").cdp.page
        await self.page.send(
            cdp_page.add_script_to_evaluate_on_new_document(
                source="""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        {name: 'Chrome PDF Plugin'},
                        {name: 'Chrome PDF Viewer'},
                        {name: 'Native Client'}
                    ]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                """
            )
        )
        log.debug("Stealth patches applied.")

    async def _import_cookies(self) -> None:
        """Load cookies from JSON backup file if it exists.

        Reads ``cookie_backup_path`` and injects cookies into the
        current browser session via CDP.  Useful for restoring sessions
        after container restart.
        """
        assert self.page is not None
        if not self.cookie_backup_path.exists():
            log.debug(
                "No cookie backup found at %s — starting fresh.",
                self.cookie_backup_path,
            )
            return

        log.info("Importing cookies from %s...", self.cookie_backup_path)
        try:
            cookies_data: list[dict[str, Any]] = json.loads(
                self.cookie_backup_path.read_text(encoding="utf-8")
            )
            cdp_cookies = __import__("nodriver.cdp").cdp.network
            for cookie in cookies_data:
                await self.page.send(
                    cdp_cookies.set_cookie(
                        name=cookie["name"],
                        value=cookie["value"],
                        domain=cookie.get("domain", ".upwork.com"),
                        path=cookie.get("path", "/"),
                        secure=cookie.get("secure", True),
                        http_only=cookie.get("httpOnly", False),
                        same_site=(
                            cdp_cookies.CookieSameSite(
                                cookie.get("sameSite", "Lax")
                            )
                            if cookie.get("sameSite")
                            else None
                        ),
                    )
                )
            log.info("Imported %d cookies.", len(cookies_data))
        except (json.JSONDecodeError, OSError, KeyError) as exc:
            log.warning(
                "Failed to import cookies from %s: %s",
                self.cookie_backup_path,
                exc,
            )

    async def _export_cookies(self) -> None:
        """Save all cookies from current session to JSON backup file.

        Retrieves cookies via CDP and writes them to
        ``cookie_backup_path`` for later restoration.  Called
        automatically on browser shutdown.
        """
        assert self.page is not None
        log.info("Exporting cookies to %s...", self.cookie_backup_path)
        try:
            cdp_cookies = __import__("nodriver.cdp").cdp.network
            cookies_raw = await self.page.send(
                cdp_cookies.get_all_cookies()
            )
            cookies_data: list[dict[str, Any]] = [
                {
                    "name": c.name,
                    "value": c.value,
                    "domain": c.domain,
                    "path": c.path,
                    "secure": c.secure,
                    "httpOnly": c.http_only,
                    "sameSite": (
                        c.same_site.value if c.same_site else None
                    ),
                }
                for c in cookies_raw
            ]
            self.cookie_backup_path.parent.mkdir(
                parents=True, exist_ok=True
            )
            self.cookie_backup_path.write_text(
                json.dumps(cookies_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            log.info("Exported %d cookies.", len(cookies_data))
        except Exception as exc:
            log.warning("Failed to export cookies: %s", exc)

    async def start_browser(self) -> None:
        """Launch Chrome and open a blank tab.

        If ``user_data_dir`` is set, persists session data (cookies,
        localStorage) across restarts.  If ``proxy_url`` is set, routes
        all traffic through the proxy.  Applies stealth patches and
        imports cookies from backup if available.
        """
        browser_args: list[str] = []
        if self.proxy_url:
            browser_args.append(f"--proxy-server={self.proxy_url}")
            log.info("Using proxy: %s", self.proxy_url)

        self.browser = await uc.start(
            browser_executable_path=self.chrome_path,
            user_data_dir=(
                str(self.user_data_dir) if self.user_data_dir else None
            ),
            browser_args=browser_args if browser_args else None,
        )
        self.page = await self.browser.get("about:blank")
        await self._apply_stealth_patches()
        await self._import_cookies()
        log.info("Browser started.")

    async def stop_browser(self) -> None:
        """Close the browser gracefully.

        Exports cookies to backup file before shutdown for session
        restoration on next run.
        """
        if self.browser:
            await self._export_cookies()
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

    async def scrape_page(
        self,
        category_uid: str,
        page: int,
        *,
        extra_params: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Scrape a single page of job listings.

        Args:
            category_uid: Upwork category UID.
            page: Page number (1-based).
            extra_params: Optional extra query parameters.

        Returns:
            List of job dicts from this page.
        """
        url = _build_url(category_uid, page, extra_params)
        jobs = await self._load_page_with_retry(url, page)

        if jobs is None:
            log.error(f"Failed to load page {page}")
            return []

        log.info(f"Page {page}: fetched {len(jobs)} jobs")
        return jobs

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


# ---------------------------------------------------------------------------
# Category discovery
# ---------------------------------------------------------------------------

#: Base URL used to open the Upwork jobs search page with the
#: category filter visible in the sidebar.  No search query is set so
#: that all top-level categories appear in the filter dropdown.
#: No query parameters needed — we only read metadata from __NUXT__.
_CATEGORY_SEARCH_BASE = "https://www.upwork.com/nx/search/jobs/"

#: JS selector for the categories filter block.
_CAT_BLOCK_SEL = '[filtername="categories"]'

#: JS selector for the dropdown toggle button inside the block.
_CAT_TOGGLE_SEL = (
    '[data-test="dropdown-toggle UpCDropdownToggle"]'
)


class CategoryScraperService:
    """Discovers Upwork category UIDs and their total job counts.

    Navigates to the Upwork jobs search page, opens the category
    filter dropdown, clicks each category option, reads the
    ``category2_uid`` from the URL and the total job count from
    ``window.__NUXT__.state.jobsSearch.paging.total``.

    Attributes:
        browser: The nodriver browser instance (set after start).
        page: The active tab (set after start).

    Example::

        svc = CategoryScraperService()
        await svc.start_browser()
        await svc.manual_cloudflare_pass()
        result = await svc.scrape_categories()
        await svc.stop_browser()
        # result == {
        #   "Web, Mobile & Software Dev": {
        #       "uid": "531770282580668418",
        #       "total_jobs": 48320,
        #   },
        # }
    """

    def __init__(
        self,
        chrome_path: str = CHROME_PATH,
        click_delay: float = 2.0,
        poll_interval: float = 1.0,
        poll_timeout: int = 20,
    ) -> None:
        """Initialise the category scraper.

        Args:
            chrome_path: Absolute path to the Chrome executable.
            click_delay: Seconds to wait after clicking a category
                option before reading the URL and NUXT state.
            poll_interval: Seconds between each DOM poll attempt.
            poll_timeout: Maximum seconds to wait for the category
                filter block to appear in the DOM.
        """
        self.chrome_path = chrome_path
        self.click_delay = click_delay
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.browser: uc.Browser | None = None
        self.page: uc.Tab | None = None

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    async def start_browser(self) -> None:
        """Launch Chrome and open a blank tab."""
        self.browser = await uc.start(
            browser_executable_path=self.chrome_path
        )
        self.page = await self.browser.get("about:blank")
        log.info("CategoryScraperService: browser started.")

    async def stop_browser(self) -> None:
        """Close the browser gracefully."""
        if self.browser:
            self.browser.stop()
            self.browser = None
            self.page = None
            log.info("CategoryScraperService: browser stopped.")

    async def manual_cloudflare_pass(self) -> None:
        """Open the Upwork search page and wait for the user.

        Navigates to the base search URL so the user can solve any
        Cloudflare challenge or cookie banner manually, then presses
        Enter to continue.
        """
        assert self.page is not None, (
            "Browser not started. Call start_browser() first."
        )
        log.info("Opening: %s", _CATEGORY_SEARCH_BASE)
        await self.page.get(_CATEGORY_SEARCH_BASE)
        input(
            ">>> Pass Cloudflare / cookie banner if needed, "
            "then press Enter: "
        )
        await self._dismiss_cookie_banner()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _dismiss_cookie_banner(self) -> None:
        """Click the OneTrust 'Accept All' button if it appears."""
        assert self.page is not None
        for _ in range(10):
            btn = await self.page.find(
                "#onetrust-accept-btn-handler"
            )
            if btn:
                log.info("Dismissing cookie banner...")
                await btn.click()
                await asyncio.sleep(2)
                return
            await asyncio.sleep(self.poll_interval)

    async def _wait_for_category_block(self) -> bool:
        """Poll until the categories filter block appears in the DOM.

        Returns:
            True if the block appeared within ``poll_timeout`` seconds,
            False otherwise.
        """
        assert self.page is not None
        log.debug(
            "Waiting for category block (up to %ds)...",
            self.poll_timeout,
        )
        for _ in range(self.poll_timeout):
            exists: bool = await self.page.evaluate(
                f"!!document.querySelector('{_CAT_BLOCK_SEL}')"
            )
            if exists:
                log.debug("Category block ready.")
                return True
            await asyncio.sleep(self.poll_interval)
        log.warning(
            "Timed out waiting for category block after %ds.",
            self.poll_timeout,
        )
        return False

    async def _ensure_dropdown_open(self) -> bool:
        """Open the category dropdown if it is currently closed.

        Returns:
            True if the dropdown is open after the call.
        """
        assert self.page is not None
        ready = await self._wait_for_category_block()
        if not ready:
            return False

        expanded: bool = await self.page.evaluate(f"""
            (function() {{
                const block = document.querySelector(
                    '{_CAT_BLOCK_SEL}'
                );
                if (!block) return false;
                const toggle = block.querySelector(
                    '{_CAT_TOGGLE_SEL}'
                );
                return toggle
                    ? toggle.getAttribute('aria-expanded') === 'true'
                    : false;
            }})()
        """)
        if expanded:
            return True

        log.debug("Category dropdown closed — clicking to open...")
        clicked: bool = await self.page.evaluate(f"""
            (function() {{
                const block = document.querySelector(
                    '{_CAT_BLOCK_SEL}'
                );
                if (!block) return false;
                const toggle = block.querySelector(
                    '{_CAT_TOGGLE_SEL}'
                );
                if (!toggle) return false;
                toggle.click();
                return true;
            }})()
        """)
        if not clicked:
            log.error("Category dropdown toggle not found.")
            return False

        await asyncio.sleep(1.5)
        expanded = await self.page.evaluate(f"""
            (function() {{
                const block = document.querySelector(
                    '{_CAT_BLOCK_SEL}'
                );
                if (!block) return false;
                const toggle = block.querySelector(
                    '{_CAT_TOGGLE_SEL}'
                );
                return toggle
                    ? toggle.getAttribute('aria-expanded') === 'true'
                    : false;
            }})()
        """)
        log.debug("Category dropdown aria-expanded: %s", expanded)
        return expanded

    @staticmethod
    def _uid_from_url(url: str) -> str | None:
        """Extract ``category2_uid`` query param from a URL.

        Args:
            url: Full URL string.

        Returns:
            The UID string, or None if not present.
        """
        from urllib.parse import parse_qs, urlparse
        params = parse_qs(urlparse(url).query)
        uids = params.get("category2_uid")
        return uids[0] if uids else None

    async def _read_total_jobs(self) -> int | None:
        """Read ``paging.total`` from ``window.__NUXT__``.

        Returns:
            Total job count reported by Upwork, or None if unavailable.
        """
        assert self.page is not None
        raw: str = await self.page.evaluate(
            "JSON.stringify(window.__NUXT__ || null)"
        )
        if not raw or raw == "null":
            return None
        try:
            nuxt: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError as exc:
            log.warning(
                "JSON parse error reading __NUXT__: %s", exc
            )
            return None
        paging: dict[str, Any] = (
            nuxt
            .get("state", {})
            .get("jobsSearch", {})
            .get("paging", {})
        )
        total = paging.get("total")
        return int(total) if total is not None else None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def inspect_single_category(
        self,
        category_name: str,
        expected_uid: str,
    ) -> dict[str, Any]:
        """Open the category dropdown, click one category, verify its UID.

        Navigates the category filter dropdown to the requested category,
        reads the ``category2_uid`` from the resulting URL, and compares
        it against ``expected_uid`` from our local registry.

        Args:
            category_name: Display name, e.g.
                ``"Web, Mobile & Software Dev"``.
            expected_uid: The UID we have stored locally, e.g.
                ``"531770282580668418"``.

        Returns:
            Dict with keys:

            - ``name`` (str): Category display name.
            - ``uid_found`` (str | None): UID read from URL after click.
            - ``uid_expected`` (str): Our locally stored UID.
            - ``uid_match`` (bool): True when both UIDs agree.
            - ``total_jobs`` (int | None): Live job count from Upwork.
            - ``load`` (CategoryLoad | None): Load classification or None
              if uid not found.

        Raises:
            RuntimeError: If the browser has not been started.
        """
        if self.page is None:
            raise RuntimeError(
                "Browser not started. Call start_browser() first."
            )

        opened = await self._ensure_dropdown_open()
        if not opened:
            log.error(
                "Category dropdown did not open — cannot inspect."
            )
            return {
                "name": category_name,
                "uid_found": None,
                "uid_expected": expected_uid,
                "uid_match": False,
                "total_jobs": None,
                "load": None,
            }

        # Read all option labels so we can find the right index.
        labels_raw: str = await self.page.evaluate(f"""
            (function() {{
                const block = document.querySelector(
                    '{_CAT_BLOCK_SEL}'
                );
                if (!block) return '';
                return Array.from(block.querySelectorAll('li'))
                    .map(el => el.innerText.trim())
                    .filter(t => t.length > 0)
                    .join('|||');
            }})()
        """)
        labels: list[str] = [
            lbl for lbl in labels_raw.split("|||") if lbl.strip()
        ]

        # Find the index for "All - <category_name>".
        target_label = f"All - {category_name}"
        target_idx: int | None = None
        for idx, label in enumerate(labels):
            if label.strip() == target_label:
                target_idx = idx
                break

        if target_idx is None:
            log.error(
                "Category '%s' not found in dropdown. "
                "Available labels: %s",
                category_name,
                [lbl for lbl in labels if lbl.startswith("All - ")],
            )
            return {
                "name": category_name,
                "uid_found": None,
                "uid_expected": expected_uid,
                "uid_match": False,
                "total_jobs": None,
                "load": None,
            }

        log.info(
            "Clicking category '%s' (index %d)...",
            category_name, target_idx,
        )
        await self.page.evaluate(f"""
            (function() {{
                const block = document.querySelector(
                    '{_CAT_BLOCK_SEL}'
                );
                if (!block) return;
                const items = block.querySelectorAll('li');
                if (items[{target_idx}]) items[{target_idx}].click();
            }})()
        """)

        await asyncio.sleep(self.click_delay)

        current_url: str = await self.page.evaluate(
            "window.location.href"
        )
        uid_found = self._uid_from_url(current_url)
        total_jobs: int | None = await self._read_total_jobs()

        uid_match = uid_found == expected_uid
        load = (
            classify_load(category_name, uid_found, total_jobs or 0)
            if uid_found
            else None
        )

        if uid_match:
            log.info(
                "UID check PASSED: %s == %s", uid_found, expected_uid
            )
        else:
            log.warning(
                "UID check FAILED: found=%s expected=%s",
                uid_found, expected_uid,
            )

        return {
            "name": category_name,
            "uid_found": uid_found,
            "uid_expected": expected_uid,
            "uid_match": uid_match,
            "total_jobs": total_jobs,
            "load": load,
        }

    async def scrape_categories(
        self,
    ) -> dict[str, dict[str, Any]]:
        """Click each category option and collect its UID + job count.

        Opens the category filter dropdown, reads all option labels,
        then iterates each one: clicks it, waits for the page to update,
        reads the ``category2_uid`` from the URL and the total job count
        from ``window.__NUXT__.state.jobsSearch.paging.total``.

        Returns:
            Mapping of top-level category label to a dict with keys:

            - ``uid`` (``str``): The ``category2_uid`` value.
            - ``total_jobs`` (``int | None``): Total vacancies on
              Upwork at the time of scraping.

            Subcategory options (those without the ``"All - "`` prefix)
            are skipped entirely.

        Raises:
            RuntimeError: If the browser has not been started.
        """
        if self.page is None:
            raise RuntimeError(
                "Browser not started. Call start_browser() first."
            )

        result: dict[str, dict[str, Any]] = {}

        # Open dropdown and read all labels before iterating
        opened = await self._ensure_dropdown_open()
        if not opened:
            log.error(
                "Category dropdown did not open — aborting."
            )
            return result

        labels_raw: str = await self.page.evaluate(f"""
            (function() {{
                const block = document.querySelector(
                    '{_CAT_BLOCK_SEL}'
                );
                if (!block) return '';
                return Array.from(block.querySelectorAll('li'))
                    .map(el => el.innerText.trim())
                    .filter(t => t.length > 0)
                    .join('|||');
            }})()
        """)
        labels: list[str] = [
            lbl for lbl in labels_raw.split("|||") if lbl.strip()
        ]
        total_labels = len(labels)
        log.info("Found %d category options.", total_labels)

        for idx, label in enumerate(labels):
            # Only process top-level categories (prefixed with "All - ").
            # Subcategory entries are skipped entirely.
            if not label.startswith("All - "):
                log.debug(
                    "[%2d/%d] Skipping subcategory: %s",
                    idx + 1, total_labels, label,
                )
                continue

            clean_label = label[len("All - "):]

            # Re-open dropdown before each click (closes after click)
            opened = await self._ensure_dropdown_open()
            if not opened:
                log.error(
                    "Dropdown could not reopen at index %d, stopping.",
                    idx,
                )
                break

            # Click the item by index via JS
            await self.page.evaluate(f"""
                (function() {{
                    const block = document.querySelector(
                        '{_CAT_BLOCK_SEL}'
                    );
                    if (!block) return;
                    const items = block.querySelectorAll('li');
                    if (items[{idx}]) items[{idx}].click();
                }})()
            """)

            # Wait for page URL + NUXT state to update
            await asyncio.sleep(self.click_delay)

            current_url: str = await self.page.evaluate(
                "window.location.href"
            )
            uid = self._uid_from_url(current_url)
            total_jobs: int | None = await self._read_total_jobs()

            if uid:
                result[clean_label] = {
                    "uid": uid,
                    "total_jobs": total_jobs,
                }
                load = classify_load(
                    clean_label, uid, total_jobs or 0
                )
                _LEVEL_ICONS = {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴"}
                icon = _LEVEL_ICONS[load.level]
                log.info(
                    "[%2d/%d] %s L%d  %-45s uid=%-20s"
                    "  total_jobs=%-6s  max_pages=%d%s",
                    idx + 1,
                    total_labels,
                    icon,
                    load.level,
                    clean_label,
                    uid,
                    f"{total_jobs:,}" if total_jobs else "n/a",
                    load.max_pages,
                    "  [splits]" if load.needs_splits else "",
                )
            else:
                log.warning(
                    "[%2d/%d] %-45s no uid in URL: %s",
                    idx + 1,
                    total_labels,
                    clean_label,
                    current_url,
                )

        log.info(
            "Category scraping done: %d/%d categories collected.",
            len(result),
            total_labels,
        )
        return result
