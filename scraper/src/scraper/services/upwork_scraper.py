"""Upwork vacancy scraper service.

Loads Upwork search pages iteratively and extracts vacancy data from
the ``window.__NUXT__.state.jobsSearch`` object embedded in each SSR
HTML page.  No internal API calls needed — the full job list is already
present in the page HTML on every load.

Features:
- Retry logic per page (up to ``max_retries`` attempts).
- Cloudflare bypass via FlareSolverr (automatic cookie injection).
- Checkpoint save after every page so progress survives crashes.
- Resume from last saved checkpoint on restart.

Classes:
- ``UpworkScraperService`` — scrapes job listings by category UID.
- ``CategoryScraperService`` — discovers all category UIDs and their
  total job counts by interacting with the Upwork search filter UI.

Usage example::

    scraper = UpworkScraperService()
    await scraper.start_browser()
    jobs = await scraper.scrape_category(
        category_uid="531770282580668418",
        max_pages=100,
    )
    await scraper.stop_browser()

    # Discover categories:
    cat_scraper = CategoryScraperService()
    await cat_scraper.start_browser()
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
import math
import os
import random
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import nodriver as uc

from scraper.categories import classify_load
from scraper.services.flaresolverr_client import FlareSolverrClient

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

# Strings that indicate Cloudflare challenge page.
# IMPORTANT: must be unique to the challenge page, NOT present in normal
# Upwork HTML.
# Confirmed false positives (present on normal Upwork pages, DO NOT ADD):
#   "cf_clearance"              — cookie name in every page's JS
#   "Just a moment"             — appears in normal Upwork content
#   "/cdn-cgi/challenge-platform" — Upwork loads challenge-platform/scripts/jsd/main.js
#                                   on ALL pages (CF Bot Management, not a challenge)
_CF_INDICATORS: tuple[str, ...] = (
    "challenges.cloudflare.com",
    "cf-browser-verification",
    "Enable JavaScript and cookies to continue",
    "Checking if the site connection is secure",
    # Upwork Cloudflare Turnstile challenge (confirmed 2026-04):
    # curl -x proxy https://upwork.com → 403 cf-mitigated:challenge
    # title is "Challenge - Upwork", page contains these unique tokens
    "<title>Challenge - Upwork</title>",
    "__cf_chl_f_tk",   # CF challenge token — only on challenge pages
    "cf_chl_opt",      # CF challenge options object — only on challenge pages
)

# Strings that indicate Upwork soft-ban / CAPTCHA / access denied
_BAN_INDICATORS: tuple[str, ...] = (
    "Access denied",
    "403 Forbidden",
    "Your access to this page has been blocked",
    "unusual traffic",
    "captcha",
    "CAPTCHA",
    "recaptcha",
    "are you a robot",
    "Are you a robot",
    "Sorry, you have been blocked",
    "Please verify you are a human",
)

# Strings that indicate Chrome's built-in network error page
# (ERR_TUNNEL_CONNECTION_FAILED, ERR_PROXY_CONNECTION_FAILED, etc.)
# Returned when FlareSolverr cannot reach the target through the proxy.
# The page is a local Chromium HTML page, NOT Upwork content.
#
# IMPORTANT: Do NOT use --google-blue-600 / --google-gray-700 alone as
# indicators — Upwork's own CSS bundle imports Google Material Design
# color tokens and these vars appear in every normal Upwork SSR page.
# Chrome built-in error pages are always tiny (< 50 KB).  Real Upwork
# SSR pages with embedded __NUXT__ JSON are 200–400 KB.  Use page size
# as the primary guard when relying on CSS variable matches.

# Definitive error codes — ONLY present on Chrome's built-in error pages,
# never in real Upwork content.
_CHROME_ERR_CODES: tuple[str, ...] = (
    "ERR_TUNNEL_CONNECTION_FAILED",
    "ERR_PROXY_CONNECTION_FAILED",
    "ERR_CONNECTION_TIMED_OUT",
    "ERR_NAME_NOT_RESOLVED",
    "ERR_CONNECTION_REFUSED",
    "ERR_EMPTY_RESPONSE",
)

# CSS variables that appear in Chromium's error page theme stylesheet.
# These can also appear in real Upwork pages via Google Material imports,
# so they are only reliable on SMALL pages (< 50 KB).
_CHROME_ERR_CSS_VARS: tuple[str, ...] = (
    "--google-blue-600",
    "--google-gray-700",
)

# Size threshold: Chrome error pages are always tiny.
# Real Upwork SSR pages are 150–400 KB.
_CHROME_ERROR_PAGE_MAX_BYTES = 50_000


def _is_chrome_error_page(html: str) -> bool:
    """Return True if the HTML is Chrome's built-in network error page.

    This happens when FlareSolverr's proxy is broken — Chrome cannot
    reach the target URL and renders a local error page instead.

    Detection rules (in priority order):
    1. Explicit ERR_* error code present → definitive error page.
    2. CSS vars match AND page is small (< 50 KB) → likely error page.
       (Large pages with these vars are legitimate Upwork content.)
    3. Title is the target domain but no upwork content → stub page.
    """
    # Rule 1: explicit network error code — definitive, size-independent
    for code in _CHROME_ERR_CODES:
        if code in html:
            log.debug("🔍 Chrome error page detected: ERR code %r found", code)
            return True

    # Rule 2: CSS vars are only reliable on small pages
    # Upwork's 200–400 KB SSR pages also contain these vars → false positives
    if len(html) < _CHROME_ERROR_PAGE_MAX_BYTES:
        css_matches = sum(1 for v in _CHROME_ERR_CSS_VARS if v in html)
        if css_matches >= 2:
            log.debug(
                "🔍 Chrome error page detected: CSS vars on small page "
                "(%d bytes, %d var matches)",
                len(html), css_matches,
            )
            return True

    # Rule 3: title is the domain name but the body has no Upwork content
    if (
        "<title>www.upwork.com</title>" in html
        and "upwork" not in html[1000:5000].lower()
    ):
        log.debug("🔍 Chrome error page detected: title/content mismatch")
        return True

    return False


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
    # Upwork treats `page=1` and omitted page as equivalent.
    # Use canonical first-page URL to reduce repetitive request signatures.
    url = (
        f"{SEARCH_BASE}"
        f"?category2_uid={category_uid}"
        f"&per_page={PER_PAGE}"
    )
    if page > 1:
        url += f"&page={page}"
    if extra_params:
        for key, value in extra_params.items():
            url += f"&{key}={value}"
    return url


def _parse_nuxt_from_html(html: str) -> dict[str, Any] | None:
    """Extract and parse ``window.__NUXT__`` directly from raw HTML.

    FlareSolverr returns the full rendered HTML of the page.  Upwork
    embeds ``window.__NUXT__`` as a ``<script>`` tag with a large JSON-
    like IIFE.  We extract the JSON payload using a regex on the
    ``__NUXT_DATA__`` or ``__NUXT__`` script tag — whichever is present.

    Upwork uses two formats depending on Nuxt version:
      - Legacy: ``window.__NUXT__=(function(a,b,...){return {...}}(...))``
      - Modern: ``<script type="application/json" id="__NUXT_DATA__">``

    Returns parsed dict or None if not found / parse error.
    """
    # Modern Nuxt 3 format: <script id="__NUXT_DATA__" type="application/json">
    m = re.search(
        r'<script[^>]+id=["\']__NUXT_DATA__["\'][^>]*>(.*?)</script>',
        html, re.DOTALL,
    )
    if m:
        try:
            raw = m.group(1).strip()
            # __NUXT_DATA__ is a special array format — try direct parse
            data = json.loads(raw)
            # If it's a list (payload format), try to find the state dict
            if isinstance(data, list):
                # Nuxt 3 payload: first element is usually the state object
                for item in data:
                    if isinstance(item, dict) and "state" in item:
                        return item
                    if isinstance(item, dict) and "jobsSearch" in item:
                        return {"state": item}
            elif isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    # Legacy Nuxt 2 format: window.__NUXT__={...} (plain JSON object)
    m = re.search(
        r'window\.__NUXT__\s*=\s*(\{.*?\})\s*;?\s*</script>',
        html, re.DOTALL,
    )
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            pass

    # Legacy IIFE format: window.__NUXT__=(function(...){return {...}}(...))
    # Too complex to eval safely — skip, rely on browser
    return None


def _extract_jobs(nuxt: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull the jobs list out of the window.__NUXT__ payload."""
    direct = (
        nuxt
        .get("state", {})
        .get("jobsSearch", {})
        .get("jobs", [])
    )
    if isinstance(direct, list) and direct:
        return direct

    # Fallback for payload shape drift: find a list of job-like dicts anywhere.
    found = _find_jobs_anywhere(nuxt)
    return found or []


def _extract_paging(nuxt: dict[str, Any]) -> dict[str, int]:
    """Pull paging metadata out of the window.__NUXT__ payload."""
    direct = (
        nuxt
        .get("state", {})
        .get("jobsSearch", {})
        .get("paging", {})
    )
    if isinstance(direct, dict) and direct:
        return direct

    # Fallback for payload shape drift (Nuxt variants / nested stores).
    return _find_paging_anywhere(nuxt) or {}


def _is_job_like(item: Any) -> bool:
    """Heuristic check for Upwork job-card objects."""
    if not isinstance(item, dict):
        return False
    has_uid = bool(item.get("uid") or item.get("ciphertext"))
    has_job_fields = any(
        k in item for k in ("title", "description", "publishedOn", "client")
    )
    return has_uid and has_job_fields


def _find_jobs_anywhere(node: Any, *, _depth: int = 0) -> list[dict[str, Any]] | None:
    """Recursively find the first list of job-like dicts in a payload."""
    if _depth > 12:
        return None

    if isinstance(node, list) and node:
        if any(_is_job_like(x) for x in node):
            return [x for x in node if isinstance(x, dict)]
        for item in node:
            found = _find_jobs_anywhere(item, _depth=_depth + 1)
            if found:
                return found
        return None

    if isinstance(node, dict):
        # Try likely keys first for speed.
        for key in ("jobs", "results", "searchResults", "items", "list"):
            if key in node:
                found = _find_jobs_anywhere(node.get(key), _depth=_depth + 1)
                if found:
                    return found
        for value in node.values():
            found = _find_jobs_anywhere(value, _depth=_depth + 1)
            if found:
                return found
    return None


def _find_paging_anywhere(node: Any, *, _depth: int = 0) -> dict[str, int] | None:
    """Recursively find paging dict ({total,count,offset,...}) in payload."""
    if _depth > 12:
        return None

    if isinstance(node, dict):
        total = node.get("total")
        if isinstance(total, int) and any(k in node for k in ("count", "offset", "per_page", "perPage")):
            return node
        for key in ("paging", "pagination", "pageInfo"):
            if key in node:
                found = _find_paging_anywhere(node.get(key), _depth=_depth + 1)
                if found:
                    return found
        for value in node.values():
            found = _find_paging_anywhere(value, _depth=_depth + 1)
            if found:
                return found
        return None

    if isinstance(node, list):
        for item in node:
            found = _find_paging_anywhere(item, _depth=_depth + 1)
            if found:
                return found
    return None


def _extract_total_from_filters(nuxt: dict[str, Any]) -> int | None:
    """Sum Experience Level filter counts to get real category total.

    Upwork stores filters in ``__NUXT__.state.jobsFilters.filters`` —
    a list of filter-group dicts.  The contractorTier group contains
    buckets for Entry Level / Intermediate / Expert whose counts sum
    to the TRUE total (not capped at 5 000 like paging.total).

    Returns the sum if found, else None.
    """
    state: dict = nuxt.get("state", {})

    # Primary path: state.jobsFilters.filters (confirmed in production)
    jobs_filters: dict = state.get("jobsFilters", {})
    filters = jobs_filters.get("filters")
    if filters and isinstance(filters, list):
        # One-time dump to see filter group names
        import json as _json
        groups_preview = [
            {"name": g.get("name") or g.get("id"), "keys": list(g.keys())[:8]}
            for g in filters if isinstance(g, dict)
        ]
        log.info("🔬 jobsFilters.filters groups: %s",
                 _json.dumps(groups_preview, ensure_ascii=False))
        total = _sum_experience_buckets(filters)
        if total:
            return total

    # Fallback: scan all state keys that look like filter containers
    for state_key, state_val in state.items():
        if not isinstance(state_val, dict):
            continue
        for val in state_val.values():
            if not isinstance(val, list):
                continue
            total = _sum_experience_buckets(val)
            if total:
                log.info(
                    "🔢 filter_total=%d found in state['%s']",
                    total, state_key,
                )
                return total

    return None


def _sum_experience_buckets(filter_groups: list) -> int:
    """Return sum of Entry/Intermediate/Expert counts if present.

    This avoids false matches from unrelated filter groups that may contain
    words like "level" and produce severe undercounts (e.g. 328 instead of 3099).
    """
    exp_tokens = ("entry", "intermediate", "expert")

    def bucket_label(b: dict[str, Any]) -> str:
        raw = (
            b.get("label")
            or b.get("name")
            or b.get("title")
            or b.get("id")
            or b.get("value")
            or ""
        )
        return str(raw).lower()

    candidates: list[tuple[int, list[tuple[str, int]]]] = []
    for group in filter_groups:
        if not isinstance(group, dict):
            continue

        buckets = (
            group.get("buckets") or group.get("options") or
            group.get("items") or group.get("values") or []
        )
        if not isinstance(buckets, list) or not buckets:
            continue

        labeled = [b for b in buckets if isinstance(b, dict)]
        if not labeled:
            continue

        # Detect real Experience Level group by bucket labels, not group name.
        # We require at least two of the canonical tokens to avoid false positives.
        labels = [bucket_label(b) for b in labeled]
        token_hits = {tok for tok in exp_tokens if any(tok in lb for lb in labels)}
        if len(token_hits) < 2:
            continue

        total = 0
        details: list[tuple[str, int]] = []
        for b in labeled:
            cnt = b.get("count") or b.get("value") or 0
            try:
                cnt_i = int(cnt)
                total += cnt_i
                details.append((bucket_label(b), cnt_i))
            except (TypeError, ValueError):
                pass

        if total > 0:
            candidates.append((total, details))

    if candidates:
        total, details = max(candidates, key=lambda item: item[0])
        log.info(
            "🔢 filter_total=%d (experience buckets: %s)",
            total,
            details,
        )
        return total

    return 0


def _is_cloudflare_block(html: str, *, _log_trigger: bool = True) -> bool:
    """Return True if the page looks like a Cloudflare challenge or ban."""
    for indicator in _CF_INDICATORS:
        if indicator in html:
            if _log_trigger:
                log.debug("🔍 CF indicator matched: %r", indicator)
            return True
    for indicator in _BAN_INDICATORS:
        if indicator in html:
            if _log_trigger:
                log.debug("🔍 BAN indicator matched: %r", indicator)
            return True
    return False


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
        # Dedicated proxy for FlareSolverr (can differ from browser proxy).
        # Fallback to scraper proxy for safer default when set.
        self.flaresolverr_proxy_url = os.environ.get(
            "FLARESOLVERR_PROXY_URL"
        ) or proxy_url
        self.cookie_backup_path = (
            cookie_backup_path or Path("data/session_cookies.json")
        )
        self.browser: uc.Browser | None = None
        self.page: uc.Tab | None = None

        # FlareSolverr client for Cloudflare bypass
        flaresolverr_url = os.environ.get(
            "FLARESOLVERR_URL", "http://localhost:8191/v1"
        )
        self.flaresolverr = FlareSolverrClient(api_url=flaresolverr_url)
        self.flaresolverr_max_timeout_ms = int(
            os.environ.get("FLARESOLVERR_MAX_TIMEOUT_MS", "120000")
        )
        self.flaresolverr_timeout_cooldown_sec = float(
            os.environ.get("FLARESOLVERR_TIMEOUT_COOLDOWN_SEC", "35")
        )
        self.flaresolverr_timeout_backoff_mult = float(
            os.environ.get("FLARESOLVERR_TIMEOUT_BACKOFF_MULT", "1.8")
        )
        self.flaresolverr_rotate_after_timeouts = int(
            os.environ.get("FLARESOLVERR_ROTATE_AFTER_TIMEOUTS", "2")
        )
        self._flaresolverr_timeout_streak = 0

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
            no_sandbox=True,  # Required for running as root in Docker
            headless=True,  # Headless mode for Docker (no Xvfb needed)
        )
        self.page = await self.browser.get("about:blank")
        await self._apply_stealth_patches()
        await self._import_cookies()
        log.info("Browser started.")

    async def _solve_cloudflare_with_flaresolverr(
        self, url: str
    ) -> dict[str, Any]:
        """Use FlareSolverr to bypass Cloudflare and get HTML directly.

        Args:
            url: Target Upwork URL to solve Cloudflare for

        Returns:
            Dict with 'html', 'cookies', 'userAgent' from FlareSolverr
        """
        log.info("🔥 Solving Cloudflare with FlareSolverr for: %s", url)
        try:
            solution = self.flaresolverr.solve(
                url=url,
                max_timeout=self.flaresolverr_max_timeout_ms,
                proxy=self.flaresolverr_proxy_url,
            )
            self._flaresolverr_timeout_streak = 0

            log.info(
                "✅ FlareSolverr solved! Cookies: %d, HTML: %d bytes",
                len(solution["cookies"]),
                len(solution.get("html", "")),
            )
            return solution

        except Exception as e:
            err = str(e)
            if self._is_flaresolverr_timeout_error(err):
                self._flaresolverr_timeout_streak += 1
                log.warning(
                    "⏱ FlareSolverr timeout streak=%d/%d",
                    self._flaresolverr_timeout_streak,
                    self.flaresolverr_rotate_after_timeouts,
                )
                if (
                    self._flaresolverr_timeout_streak
                    >= self.flaresolverr_rotate_after_timeouts
                ):
                    self._rotate_flaresolverr_proxy_session()
                    self._flaresolverr_timeout_streak = 0
            log.error("❌ FlareSolverr failed: %s", e)
            raise RuntimeError(
                f"Could not bypass Cloudflare with FlareSolverr: {e}"
            ) from e

    @staticmethod
    def _is_flaresolverr_timeout_error(error_text: str) -> bool:
        text = error_text.lower()
        return (
            "timeout after" in text
            and "error solving the challenge" in text
        ) or (
            "flaresolverr http error 500" in text and "timeout" in text
        )

    @staticmethod
    def _with_rotated_session(username: str) -> str | None:
        # Support usernames that already include session token.
        if "session-" in username:
            base = username.split("session-", 1)[0]
            token = f"vm{int(time.time())}{random.randint(1000,9999)}"
            return f"{base}session-{token}"

        # Webshare style supports adding session token suffix.
        if "-country-" in username or "-us-" in username:
            token = f"vm{int(time.time())}{random.randint(1000,9999)}"
            return f"{username}-session-{token}"

        return None

    def _rotate_flaresolverr_proxy_session(self) -> None:
        proxy = self.flaresolverr_proxy_url
        if not proxy:
            return

        parsed = urlsplit(proxy)
        if (
            not parsed.scheme
            or not parsed.hostname
            or not parsed.port
            or not parsed.username
        ):
            log.warning("Cannot rotate proxy session: invalid proxy URL format")
            return

        rotated_user = self._with_rotated_session(parsed.username)
        if not rotated_user:
            log.warning(
                "Proxy session rotation skipped: username has no session pattern"
            )
            return

        auth = quote(rotated_user, safe="")
        if parsed.password:
            auth = f"{auth}:{quote(parsed.password, safe='')}"
        netloc = f"{auth}@{parsed.hostname}:{parsed.port}"
        rotated_proxy = urlunsplit(
            (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
        )

        self.flaresolverr_proxy_url = rotated_proxy
        if self.proxy_url == proxy:
            self.proxy_url = rotated_proxy
        log.warning("🔁 Rotated FlareSolverr proxy session username")

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
        jobs, _ = await self.scrape_page_with_paging(
            category_uid, page, extra_params=extra_params
        )
        return jobs

    async def scrape_page_with_paging(
        self,
        category_uid: str,
        page: int,
        *,
        extra_params: dict[str, str] | None = None,
    ) -> tuple[list[dict[str, Any]] | None, dict[str, int]]:
        """Scrape a single page and return (jobs, paging_info).

        ``paging_info`` is the raw ``paging`` dict from __NUXT__:
        ``{"total": 2543, "count": 50, "offset": 150, ...}``

        Use ``paging["total"]`` to know the real total job count for the
        category, which lets the caller compute the actual max page number:
        ``max_page = min(100, math.ceil(paging["total"] / 50))``.

        Args:
            category_uid: Upwork category UID.
            page: Page number (1-based).
            extra_params: Optional extra query parameters.

        Returns:
            Tuple of (jobs list or None, paging dict).
            Returns (None, {}) when all retries failed (load error).
            Returns ([], paging) when page loaded but had 0 jobs
            (genuine empty page / beyond category limit).
            paging is empty dict if paging data was unavailable.
        """
        url = _build_url(category_uid, page, extra_params)
        jobs, paging = await self._load_page_with_retry_and_paging(
            url, page
        )

        if jobs is None:
            log.error(f"Failed to load page {page}")
            return None, {}

        log.info(f"Page {page}: fetched {len(jobs)} jobs")
        return jobs, paging

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

        Upwork ships ``window.__NUXT__`` as an IIFE:
            window.__NUXT__ = (function(a,b,...){return {...}}(v1,v2,...))
        The browser evaluates the IIFE immediately on page load, so by the
        time we call this method ``window.__NUXT__`` should already be a
        plain object.  But just in case it's still a callable (e.g. the
        script tag hasn't finished), we invoke it ourselves.

        Returns:
            Parsed dict, or None if unavailable.
        """
        assert self.page is not None
        raw: str = await self.page.evaluate(
            """
            (function() {
                try {
                    var n = window.__NUXT__;
                    if (!n) return null;
                    if (typeof n === 'function') { n = n(); }
                    return JSON.stringify(n);
                } catch(e) {
                    return null;
                }
            })()
            """
        )
        if not raw or raw == "null":
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            log.error("JSON parse error in __NUXT__: %s", exc)
            return None

    async def _inject_flaresolverr_cookies(
        self,
        cookies: list[dict[str, Any]],
        user_agent: str = "",
    ) -> None:
        """Inject FlareSolverr cookies + user-agent into the nodriver browser.

        Uses CDP ``Network.setCookie`` for each cookie and
        ``Network.setUserAgentOverride`` so subsequent requests look like
        the same browser that solved Cloudflare.

        Args:
            cookies: List of cookie dicts from FlareSolverr response.
                     Expected keys: name, value, domain, path,
                     secure, httpOnly.
            user_agent: User-Agent string returned by FlareSolverr.
        """
        assert self.page is not None
        cdp_network = __import__("nodriver.cdp").cdp.network

        injected = 0
        for cookie in cookies:
            try:
                await self.page.send(
                    cdp_network.set_cookie(
                        name=cookie["name"],
                        value=cookie["value"],
                        domain=cookie.get("domain", ".upwork.com"),
                        path=cookie.get("path", "/"),
                        secure=cookie.get("secure", True),
                        http_only=cookie.get("httpOnly", False),
                        same_site=(
                            cdp_network.CookieSameSite(
                                cookie["sameSite"]
                            )
                            if cookie.get("sameSite")
                            else None
                        ),
                    )
                )
                injected += 1
            except Exception as exc:
                log.warning(
                    "Failed to inject cookie %s: %s",
                    cookie.get("name"), exc,
                )

        if user_agent:
            try:
                await self.page.send(
                    cdp_network.set_user_agent_override(user_agent=user_agent)
                )
                log.debug("User-Agent set to: %s", user_agent[:80])
            except Exception as exc:
                log.warning("Failed to set user-agent: %s", exc)

        log.info(
            "🍪 Injected %d/%d FlareSolverr cookies into browser session.",
            injected, len(cookies),
        )

    async def _hard_navigate(self, url: str) -> None:
        """Navigate to ``url`` with a guaranteed full page reload.

        Upwork uses Nuxt/Vue SSG — when the browser is already on
        ``upwork.com`` and we call ``page.get(url)`` for a different
        search page, the framework intercepts the navigation and does a
        client-side SPA transition.  In that case ``window.__NUXT__``
        keeps the *old* state and the new jobs never appear in the DOM.

        Fix: bounce through ``about:blank`` first so the next navigation
        to the Upwork URL is always a fresh full HTTP request, not a
        SPA route change.  This guarantees a new ``__NUXT__`` payload.
        """
        assert self.page is not None
        await self.page.get("about:blank")
        await asyncio.sleep(0.3)
        await self.page.get(url)

    async def _poll_for_nuxt(
        self,
        page_num: int,
        *,
        timeout: float = 45.0,
        interval: float = 2.0,
    ) -> dict[str, Any] | None:
        """Poll ``window.__NUXT__`` every ``interval`` seconds.

        Upwork hydrates its Vuex/Pinia store asynchronously after the
        initial page load.  A fixed ``asyncio.sleep`` often races with
        this hydration.  This method polls until either:
        - ``window.__NUXT__`` is available (returns it immediately), or
        - ``timeout`` seconds elapse (returns None).

        Args:
            page_num: Page number for log messages.
            timeout: Maximum seconds to wait before giving up.
            interval: Seconds between each poll.

        Returns:
            Parsed ``__NUXT__`` dict, or ``None`` if timed out.
        """
        assert self.page is not None
        elapsed = 0.0
        while elapsed < timeout:
            nuxt = await self._get_nuxt()
            if nuxt is not None:
                jobs = _extract_jobs(nuxt)
                log.info(
                    "⏱️  [page %d] __NUXT__ ready after %.0fs "
                    "(%d jobs in state)",
                    page_num, elapsed, len(jobs),
                )
                return nuxt
            await asyncio.sleep(interval)
            elapsed += interval
        log.warning(
            "⏱️  [page %d] __NUXT__ still None after %.0fs timeout",
            page_num, timeout,
        )
        return None

    async def _load_page_with_retry(
        self,
        url: str,
        page_num: int,
    ) -> list[dict[str, Any]] | None:
        """Load page and return jobs only (backward-compat wrapper)."""
        jobs, _ = await self._load_page_with_retry_and_paging(url, page_num)
        return jobs

    async def _load_page_with_retry_and_paging(
        self,
        url: str,
        page_num: int,
    ) -> tuple[list[dict[str, Any]] | None, dict[str, int]]:
        """Load a single Upwork search page via FlareSolverr and extract jobs.

        Strategy:
        1. FlareSolverr fetches the page through the residential proxy,
           solving the Cloudflare challenge if needed.
        2. The returned HTML is written into the nodriver Chrome tab via
           ``document.write()`` so that inline ``<script>`` tags execute
           and ``window.__NUXT__`` becomes available.
        3. ``_get_nuxt()`` reads ``window.__NUXT__`` from the live DOM.

        Chrome never navigates to Upwork directly — it only executes the
        HTML that FlareSolverr already fetched.  This avoids Cloudflare
        detecting the headless browser.

        Args:
            url: Full Upwork search URL.
            page_num: Page number (for logging).

        Returns:
            Tuple of (jobs list or None on failure, paging dict).
        """
        assert self.page is not None

        for attempt in range(1, self.max_retries + 1):
            backoff = self.retry_delay * (3 ** (attempt - 1))

            try:
                # ── Step 1: FlareSolverr fetches + solves CF ───────────
                solution = await self._solve_cloudflare_with_flaresolverr(url)
                html = solution.get("html", "")

                if not html:
                    log.warning(
                        "FlareSolverr returned empty HTML "
                        "for page %d (attempt %d/%d)",
                        page_num, attempt, self.max_retries,
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(backoff)
                    continue

                # ── Detect Chrome network error page (broken proxy) ────
                if _is_chrome_error_page(html):
                    # Log first 300 chars of HTML to help diagnose
                    log.error(
                        "🔌 FlareSolverr proxy BROKEN on page %d "
                        "(attempt %d/%d) — Chrome error page (%d bytes). "
                        "HTML preview: %.300s",
                        page_num, attempt, self.max_retries, len(html),
                        html[:300].replace("\n", " "),
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(backoff)
                    continue

                # ── Detect Cloudflare / ban page ───────────────────────
                if _is_cloudflare_block(html):
                    log.error(
                        "🚫 FlareSolverr could not bypass Cloudflare "
                        "on page %d (attempt %d/%d)",
                        page_num, attempt, self.max_retries,
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(backoff)
                    continue

                log.info(
                    "� [page %d] FlareSolverr HTML: %d bytes, cookies: %d",
                    page_num, len(html), len(solution.get("cookies", [])),
                )

                # ── Step 2: write HTML into Chrome so scripts execute ──
                await self.page.evaluate(
                    f"document.open(); "
                    f"document.write({json.dumps(html)}); "
                    f"document.close();"
                )
                await asyncio.sleep(2)  # let inline scripts run

                # ── Step 3: extract window.__NUXT__ ───────────────────
                nuxt = await self._get_nuxt()

                if nuxt is None:
                    # Try parsing directly from raw HTML as fallback
                    nuxt_from_html = _parse_nuxt_from_html(html)
                    if nuxt_from_html is not None:
                        log.info(
                            "⚠️  [page %d] __NUXT__ not in browser JS, "
                            "but found in raw HTML — using HTML parse",
                            page_num,
                        )
                        nuxt = nuxt_from_html
                    else:
                        log.warning(
                            "No __NUXT__ after document.write on page %d "
                            "(attempt %d/%d). "
                            "HTML preview: %.300s",
                            page_num, attempt, self.max_retries,
                            html[:300].replace("\n", " "),
                        )
                        if attempt < self.max_retries:
                            await asyncio.sleep(backoff)
                        continue

                jobs = _extract_jobs(nuxt)
                paging = _extract_paging(nuxt)

                filter_total = _extract_total_from_filters(nuxt)
                if filter_total:
                    paging = dict(paging)
                    paging["filter_total"] = filter_total
                    log.info(
                        "🔢 [page %d] filter_total=%d (paging.total=%d)",
                        page_num, filter_total, paging.get("total", 0),
                    )

                # If the page is empty but totals say it should exist, retry.
                total_jobs = paging.get("filter_total") or paging.get("total")
                if total_jobs and not jobs:
                    max_page = min(100, math.ceil(total_jobs / PER_PAGE))
                    if page_num <= max_page:
                        log.warning(
                            "Empty jobs on page %d but total=%d suggests data; retrying",
                            page_num,
                            total_jobs,
                        )
                        if attempt < self.max_retries:
                            await asyncio.sleep(backoff)
                            continue
                        return None, {}

                # Ambiguous response: no jobs and no total metadata.
                # Treat as transient parse/load failure, not a real empty page.
                if not jobs and not total_jobs:
                    log.warning(
                        "Ambiguous empty payload on page %d (no jobs, no totals) "
                        "attempt %d/%d; retrying",
                        page_num,
                        attempt,
                        self.max_retries,
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(backoff)
                        continue
                    return None, {}

                return jobs, paging

            except Exception as e:
                timeout_hit = self._is_flaresolverr_timeout_error(str(e))
                log.error(
                    "Error loading page %d (attempt %d/%d): %s",
                    page_num, attempt, self.max_retries, e,
                )
                if attempt < self.max_retries:
                    delay = backoff
                    if timeout_hit:
                        timeout_backoff = (
                            self.flaresolverr_timeout_cooldown_sec
                            * (self.flaresolverr_timeout_backoff_mult ** (attempt - 1))
                        )
                        delay = max(delay, timeout_backoff)
                        log.warning(
                            "⏳ Timeout cooldown before retry: %.1fs",
                            delay,
                        )
                    await asyncio.sleep(delay)
                continue

        log.error(
            "Page %d failed after %d attempts.", page_num, self.max_retries
        )
        return None, {}

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
            if total_reported is None and jobs:
                # FlareSolverr HTML doesn't give us paging info easily
                # Just log that we're scraping
                log.info("Starting to scrape category %s", category_uid)

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
