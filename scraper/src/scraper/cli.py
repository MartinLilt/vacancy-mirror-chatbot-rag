"""Entry point for the scraper container.

Commands
--------
scrape-categories   Scrape UIDs + job counts for all top-level categories.
scrape              Scrape job listings for a specific category UID.
inspect-category    Open the Upwork dropdown, click one category, verify
                    its UID against our registry and print a load report.
warmup              Warm up browser session by visiting public pages to
                    establish cookies and avoid Cloudflare detection.

Usage (inside container)::

    python -m scraper.cli scrape-categories
    python -m scraper.cli scrape --uid 531770282580668418 --label webdev
    python -m scraper.cli inspect-category \\
        --name "Web, Mobile & Software Dev" \\
        --expected-uid 531770282580668418
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import sys

from scraper.categories import CATEGORY_UIDS
from scraper.services.postgres import ScraperPostgresService
from scraper.services.upwork_scraper import (
    CategoryScraperService,
    UpworkScraperService,
    MAX_ALLOWED_PAGE,
    PER_PAGE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)

_LEVEL_ICONS: dict[int, str] = {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴"}


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="python -m scraper.cli",
        description="Upwork scraper — container entry point.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── scrape-categories ────────────────────────────────────────────
    sub.add_parser(
        "scrape-categories",
        help="Collect UIDs and job counts for all top-level categories.",
    )

    # ── scrape ───────────────────────────────────────────────────────
    scrape_p = sub.add_parser(
        "scrape",
        help="Scrape job listings for a single category.",
    )
    scrape_p.add_argument(
        "--uid",
        required=True,
        help="Upwork category UID.",
    )
    scrape_p.add_argument(
        "--label",
        default=None,
        help=(
            "Human-readable label (defaults to name from CATEGORY_UIDS)."
        ),
    )
    scrape_p.add_argument(
        "--max-pages",
        type=int,
        default=MAX_ALLOWED_PAGE,
        metavar="N",
        help=f"Max pages to scrape (default: {MAX_ALLOWED_PAGE}).",
    )
    scrape_p.add_argument(
        "--start-page",
        type=int,
        default=1,
        metavar="N",
        help="Start from page N (for resume from checkpoint).",
    )
    scrape_p.add_argument(
        "--delay-min",
        type=int,
        default=30,
        metavar="SEC",
        help="Minimum delay between pages in seconds (default: 30).",
    )
    scrape_p.add_argument(
        "--delay-max",
        type=int,
        default=45,
        metavar="SEC",
        help="Maximum delay between pages in seconds (default: 45).",
    )
    scrape_p.add_argument(
        "--stop-at-hour",
        type=int,
        default=22,
        metavar="HOUR",
        help="Stop scraping at hour N (24h format, default: 22).",
    )
    scrape_p.add_argument(
        "--max-runtime-minutes",
        type=int,
        default=None,
        metavar="MIN",
        help=(
            "Maximum runtime in minutes (e.g., 45). "
            "Scraper will stop after this duration to avoid overlaps. "
            "If not set, runs until completion or stop-at-hour."
        ),
    )
    scrape_p.add_argument(
        "--db-url",
        default=None,
        metavar="URL",
        help=(
            "PostgreSQL connection URL. "
            "Falls back to DATABASE_URL env var."
        ),
    )
    scrape_p.add_argument(
        "--user-data-dir",
        default=None,
        metavar="PATH",
        help=(
            "Chrome User Data Directory for session persistence. "
            "If not set, Chrome runs in ephemeral mode."
        ),
    )
    scrape_p.add_argument(
        "--proxy-url",
        default=None,
        metavar="URL",
        help=(
            "Residential proxy URL (format: http://user:pass@host:port). "
            "If not set, uses server's direct IP. "
            "Falls back to PROXY_URL env var."
        ),
    )
    scrape_p.add_argument(
        "--cookie-backup",
        default=None,
        metavar="PATH",
        help=(
            "Path to save/load cookies as JSON backup. "
            "Default: data/session_cookies.json"
        ),
    )

    # ── scrape-chaos ─────────────────────────────────────────────────
    chaos_p = sub.add_parser(
        "scrape-chaos",
        help=(
            "Chaotic multi-category scraper: visits all 12 categories in "
            "random order, random pages, remembers progress, stops at time limit."
        ),
    )
    chaos_p.add_argument(
        "--max-pages-per-cat",
        type=int,
        default=5,
        metavar="N",
        help="Max pages to collect per category per session (default: 5).",
    )
    chaos_p.add_argument(
        "--target-per-cat",
        type=int,
        default=1000,
        metavar="N",
        help=(
            "Target number of jobs per category (default: 1000). "
            "Stops collecting once reached."
        ),
    )
    chaos_p.add_argument(
        "--delay-min",
        type=int,
        default=15,
        metavar="SEC",
        help="Minimum delay between pages in seconds (default: 15).",
    )
    chaos_p.add_argument(
        "--delay-max",
        type=int,
        default=90,
        metavar="SEC",
        help="Maximum delay between pages in seconds (default: 90).",
    )
    chaos_p.add_argument(
        "--stop-at-hour",
        type=int,
        default=22,
        metavar="HOUR",
        help="Stop scraping at hour N (24h format, default: 22).",
    )
    chaos_p.add_argument(
        "--max-runtime-minutes",
        type=int,
        default=50,
        metavar="MIN",
        help="Maximum runtime in minutes (default: 50).",
    )
    chaos_p.add_argument(
        "--state-file",
        default="/app/data/chaos_state.json",
        metavar="PATH",
        help="Path to JSON state file tracking per-category progress.",
    )
    chaos_p.add_argument(
        "--reset",
        action="store_true",
        help="Reset all state and start fresh (ignores saved progress).",
    )
    chaos_p.add_argument(
        "--db-url",
        default=None,
        metavar="URL",
        help="PostgreSQL connection URL. Falls back to DATABASE_URL env var.",
    )
    chaos_p.add_argument(
        "--user-data-dir",
        default=None,
        metavar="PATH",
        help="Chrome User Data Directory for session persistence.",
    )
    chaos_p.add_argument(
        "--proxy-url",
        default=None,
        metavar="URL",
        help="Residential proxy URL. Falls back to PROXY_URL env var.",
    )

    # ── warmup ───────────────────────────────────────────────────────
    warmup_p = sub.add_parser(
        "warmup",
        help=(
            "Warm up browser session by visiting public pages "
            "(Upwork + general web) to establish cookies and avoid "
            "Cloudflare detection before scraping."
        ),
    )
    warmup_p.add_argument(
        "--proxy-url",
        default=None,
        metavar="URL",
        help=(
            "Residential proxy URL (format: http://user:pass@host:port). "
            "Falls back to PROXY_URL env var."
        ),
    )
    warmup_p.add_argument(
        "--user-data-dir",
        default=None,
        metavar="PATH",
        help="Chrome User Data Directory for session persistence.",
    )
    warmup_p.add_argument(
        "--cookie-backup",
        default=None,
        metavar="PATH",
        help="Path to save cookies as JSON backup.",
    )

    # ── inspect-category ─────────────────────────────────────────────
    inspect_p = sub.add_parser(
        "inspect-category",
        help=(
            "Open the Upwork category dropdown, click one category, "
            "verify its UID, and print a load classification report."
        ),
    )
    inspect_p.add_argument(
        "--name",
        default="Web, Mobile & Software Dev",
        help=(
            "Category display name (default: "
            "'Web, Mobile & Software Dev')."
        ),
    )
    inspect_p.add_argument(
        "--expected-uid",
        default=None,
        help=(
            "Expected category2_uid. Defaults to the value from "
            "our local CATEGORY_UIDS registry."
        ),
    )

    return parser.parse_args()


def _print_load_report(result: dict) -> None:
    """Print a formatted load classification table for one category."""
    load = result.get("load")
    name: str = result["name"]
    total_jobs: int | None = result.get("total_jobs")
    uid_found: str | None = result.get("uid_found")
    uid_expected: str = result["uid_expected"]
    uid_match: bool = result.get("uid_match", False)

    sep = "-" * 68
    print(sep)
    print(
        f" {'#':<3} {'Lvl':<5} {'Icon':<5} {'Total jobs':<12} "
        f"{'max_pages':<10} {'Splits':<8} {'+Replica':<10} Category"
    )
    print(sep)

    if load is not None:
        icon = _LEVEL_ICONS.get(load.level, "?")
        total_str = (
            f"{total_jobs:,}" if total_jobs is not None else "n/a"
        )
        splits = "yes" if load.needs_splits else "no"
        replica = "yes" if load.needs_extra_replica else "no"
        print(
            f" {'1':<3} L{load.level:<4} {icon:<5} {total_str:<12} "
            f"{load.max_pages:<10} {splits:<8} {replica:<10} {name}"
        )
    else:
        print("  ⚠️  Could not determine load — UID not found in URL")

    print(sep)
    print()

    # UID verification result
    if uid_match:
        print(f"  ✅ UID verified: {uid_found} == {uid_expected}")
    else:
        print("  ❌ UID MISMATCH!")
        print(f"     Found in URL : {uid_found or 'n/a'}")
        print(f"     Expected     : {uid_expected}")
        print(
            "     ⚠️  Update CATEGORY_UIDS in categories.py "
            "if Upwork changed the UID."
        )
    print()


async def _cmd_scrape_categories() -> None:
    """Run the category discovery scrape."""
    service = CategoryScraperService()
    results = await service.scrape_categories()
    log.info(
        "Scraped %d categories.",
        len(results),
    )
    for cat in results:
        log.info(
            "  %-40s uid=%-20s total_jobs=%d",
            cat["name"],
            cat["uid"],
            cat["total_jobs"],
        )


async def _cmd_scrape(args: argparse.Namespace) -> None:
    """Scrape job listings for a single category, save to PostgreSQL.

    Supports:
    - Resume from checkpoint (--start-page)
    - Random delays between pages (--delay-min, --delay-max)
    - Stop at specific hour (--stop-at-hour)
    """
    import random
    from datetime import datetime
    from scraper.state import ScraperState

    db_url: str | None = (
        args.db_url
        if hasattr(args, "db_url") and args.db_url
        else __import__("os").environ.get("DATABASE_URL")
    )

    # Resolve proxy URL from CLI arg or env var
    proxy_url: str | None = (
        args.proxy_url
        if hasattr(args, "proxy_url") and args.proxy_url
        else __import__("os").environ.get("PROXY_URL")
    )

    # Resolve user_data_dir, cookie_backup from CLI
    user_data_dir = (
        __import__("pathlib").Path(args.user_data_dir)
        if hasattr(args, "user_data_dir") and args.user_data_dir
        else None
    )
    cookie_backup = (
        __import__("pathlib").Path(args.cookie_backup)
        if hasattr(args, "cookie_backup") and args.cookie_backup
        else None
    )

    # Resolve category name from UID (best-effort, for DB record).
    uid_to_name: dict[str, str] = {
        v: k for k, v in CATEGORY_UIDS.items()
    }
    category_name: str = uid_to_name.get(
        args.uid, args.label or args.uid
    )

    # Initialize state manager
    state = ScraperState(
        category_uid=args.uid,
        category_name=category_name,
    )

    # Monday? Reset state
    if datetime.now().weekday() == 0:  # 0 = Monday
        log.info("Monday detected — resetting state for new week")
        state.reset_for_new_week()

    # Load checkpoint
    checkpoint = state.load_checkpoint()
    start_page = max(args.start_page, checkpoint.get("current_page", 1))
    log.info(f"Starting from page {start_page}")

    db: ScraperPostgresService | None = None
    run_id: int | None = None

    if db_url:
        try:
            db = ScraperPostgresService(db_url)
            run_id = db.start_scrape_run(
                category_uid=args.uid,
                category_name=category_name,
            )
        except Exception as exc:
            log.error("DB connection failed: %s", exc)
            db = None
    else:
        log.warning(
            "DATABASE_URL not set — results will NOT be saved to DB."
        )

    service = UpworkScraperService(
        page_delay_min=float(args.delay_min),
        page_delay_max=float(args.delay_max),
        user_data_dir=user_data_dir,
        proxy_url=proxy_url,
        cookie_backup_path=cookie_backup,
    )
    await service.start_browser()

    status = "failed"
    jobs: list[dict] = []
    pages_scraped = 0
    total_inserted = 0
    total_skipped = 0

    # Track start time for runtime limit
    scrape_start_time = datetime.now()
    max_runtime_seconds = (
        args.max_runtime_minutes * 60
        if args.max_runtime_minutes
        else None
    )

    try:
        # Scrape page by page with delays and time checks
        for page in range(start_page, args.max_pages + 1):
            # Check runtime limit (if set)
            if max_runtime_seconds is not None:
                elapsed_seconds = (
                    datetime.now() - scrape_start_time
                ).total_seconds()
                if elapsed_seconds >= max_runtime_seconds:
                    log.info(
                        f"Reached runtime limit "
                        f"({args.max_runtime_minutes} min), "
                        f"stopping at page {page - 1}"
                    )
                    break

            # Check if we should stop (time limit)
            current_hour = datetime.now().hour
            if current_hour >= args.stop_at_hour:
                log.info(
                    f"Reached stop hour {args.stop_at_hour}:00, "
                    f"stopping at page {page - 1}"
                )
                break

            log.info(
                f"Scraping page {page}/{args.max_pages} "
                f"(hour: {current_hour}:xx)"
            )

            # Scrape single page
            page_jobs = await service.scrape_page(
                category_uid=args.uid,
                page=page,
            )

            if not page_jobs:
                log.warning(f"No jobs on page {page}, stopping")
                break

            jobs.extend(page_jobs)
            pages_scraped = page

            # Save checkpoint after each page
            state.save_checkpoint(
                current_page=page,
                total_pages=args.max_pages,
                level=1,  # TODO: detect level dynamically
                completed=(page >= args.max_pages),
            )

            # Insert to DB immediately (incremental)
            if db is not None and run_id is not None:
                inserted = db.insert_raw_jobs(
                    jobs=page_jobs,
                    scrape_run_id=run_id,
                    category_uid=args.uid,
                    category_name=category_name,
                )
                total_inserted += inserted
                total_skipped += len(page_jobs) - inserted
                log.info(f"Inserted {inserted} jobs from page {page}")

            # Delay before next page (except on last page)
            if page < args.max_pages:
                delay = random.randint(args.delay_min, args.delay_max)
                log.info(f"Waiting {delay} seconds...")
                await __import__("asyncio").sleep(delay)

        status = "done"

    except Exception as exc:
        log.error("Scraping error: %s", exc)

    finally:
        await service.stop_browser()

    if db is not None and run_id is not None:
        db.finish_scrape_run(
            run_id=run_id,
            pages_collected=pages_scraped,
            jobs_collected=len(jobs),
            jobs_inserted=total_inserted,
            jobs_skipped=total_skipped,
            status=status,
        )
        db.close()

    log.info(
        "Scrape complete: %d jobs collected from %d pages.",
        len(jobs),
        pages_scraped,
    )


def _print_jobs(
    jobs: list[dict],
    *,
    category_name: str = "",
) -> None:
    """Print collected jobs to stdout for inspection.

    Args:
        jobs: List of raw job dicts from the scraper.
        category_name: Category label shown in the header.
    """
    _TYPE = {1: "fixed", 2: "hourly"}
    total = len(jobs)
    sep = "=" * 72
    print()
    print(sep)
    print(
        f"  {total} jobs collected"
        + (f"  |  {category_name}" if category_name else "")
    )
    print(sep)

    for i, job in enumerate(jobs, start=1):
        title: str = job.get("title") or "n/a"
        published: str = (job.get("publishedOn") or "")[:10] or "n/a"
        job_type_int: int | None = job.get("type")
        job_type: str = _TYPE.get(job_type_int, "n/a")
        duration: str = job.get("durationLabel") or "n/a"
        enterprise: bool = bool(job.get("enterpriseJob"))

        # client
        client: dict = job.get("client") or {}
        loc = client.get("location") or {}
        country: str = (
            loc.get("country") if isinstance(loc, dict) else None
        ) or "n/a"
        payment_ok: str = (
            "✅" if client.get("isPaymentVerified") else "❌"
        )
        spent = client.get("totalSpent")
        spent_str: str = f"${spent:,.0f}" if spent else "n/a"
        reviews = client.get("totalReviews")
        reviews_str: str = str(reviews) if reviews else "n/a"
        feedback = client.get("totalFeedback")
        feedback_str: str = (
            f"{feedback:.2f}" if feedback else "n/a"
        )

        # skills from attrs
        attrs: list = job.get("attrs") or []
        skills: list[str] = [
            a["prefLabel"]
            for a in attrs
            if isinstance(a, dict) and a.get("prefLabel")
        ]
        skills_str: str = ", ".join(skills[:6]) or "n/a"

        # budget
        hourly: dict = job.get("hourlyBudget") or {}
        h_min = hourly.get("min") or 0
        h_max = hourly.get("max") or 0
        weekly: dict = job.get("weeklyBudget") or {}
        w_amt = weekly.get("amount") or 0

        if job_type == "hourly" and h_max:
            budget_str = f"${h_min}–${h_max}/hr"
        elif job_type == "hourly" and w_amt:
            budget_str = f"${w_amt}/wk"
        elif job_type == "fixed":
            fixed = (job.get("amount") or {}).get("amount") or 0
            budget_str = f"${fixed}" if fixed else "n/a"
        else:
            budget_str = "n/a"

        enterprise_str = " [ENTERPRISE]" if enterprise else ""

        desc: str = (
            (job.get("description") or "")
            .replace("\n", " ")
            .replace("<span class=\"highlight\">", "")
            .replace("</span>", "")
            .strip()
        )
        desc_preview: str = (
            desc[:160] + "…" if len(desc) > 160 else desc
        ) or "n/a"

        print(
            f"\n[{i:>3}] {title}{enterprise_str}"
            f"\n      published={published}  type={job_type}"
            f"  budget={budget_str}  duration={duration}"
            f"\n      client: country={country}  payment={payment_ok}"
            f"  spent={spent_str}  reviews={reviews_str}"
            f"  feedback={feedback_str}"
            f"\n      skills: [{skills_str}]"
            f"\n      desc: {desc_preview}"
        )

    print()
    print(sep)
    print()


async def _cmd_inspect_category(args: argparse.Namespace) -> None:
    """Open Upwork, click one category, verify UID, print report."""
    name: str = args.name
    expected_uid: str = (
        args.expected_uid
        or CATEGORY_UIDS.get(name, "")
    )

    if not expected_uid:
        log.error(
            "Category '%s' not found in CATEGORY_UIDS registry "
            "and --expected-uid was not provided.",
            name,
        )
        sys.exit(1)

    log.info(
        "Inspecting category '%s' (expected uid=%s).",
        name, expected_uid,
    )

    service = CategoryScraperService()
    await service.start_browser()
    await service.manual_cloudflare_pass()

    result = await service.inspect_single_category(
        category_name=name,
        expected_uid=expected_uid,
    )

    await service.stop_browser()

    _print_load_report(result)

    if not result.get("uid_match"):
        sys.exit(2)


async def _cmd_scrape_chaos(args: argparse.Namespace) -> None:
    """Chaotic multi-category scraper.

    Strategy:
    - Loads/saves state from JSON file (per-category pages visited + jobs count)
    - Each session: shuffles categories by priority (least collected first),
      picks random pages (not sequential), scrapes until time limit
    - Respects per-category target (stops visiting a category once target reached)
    - Respects real page limit from Upwork (never exceeds available pages)
    - Inserts all collected jobs to PostgreSQL immediately
    """
    import json
    import os
    import random
    from datetime import datetime
    from pathlib import Path

    # ── Config ────────────────────────────────────────────────────────
    db_url: str | None = args.db_url or os.environ.get("DATABASE_URL")
    proxy_url: str | None = args.proxy_url or os.environ.get("PROXY_URL")
    user_data_dir = Path(args.user_data_dir) if args.user_data_dir else None
    state_path = Path(args.state_file)
    max_runtime_sec = args.max_runtime_minutes * 60
    start_time = datetime.now()

    # All 12 categories: name → uid
    all_cats = list(CATEGORY_UIDS.items())  # [(name, uid), ...]

    # ── State: { uid: { "collected": int, "visited_pages": [int, ...] } } ──
    def load_state() -> dict:
        if state_path.exists() and not args.reset:
            try:
                with open(state_path) as f:
                    return json.load(f)
            except Exception:
                pass
        # Fresh state
        return {
            uid: {
                "collected": 0,
                "visited_pages": [],
                "total_upwork_jobs": 0,
            }
            for _, uid in all_cats
        }

    def save_state(state: dict) -> None:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = state_path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
        tmp.replace(state_path)  # atomic rename — safe against kill mid-write

    def elapsed_seconds() -> float:
        return (datetime.now() - start_time).total_seconds()

    def time_ok() -> bool:
        if elapsed_seconds() >= max_runtime_sec:
            return False
        if datetime.now().hour >= args.stop_at_hour:
            return False
        return True

    def apply_paging_totals(
        cat_state: dict,
        cat_name: str,
        paging: dict[str, int],
        *,
        source: str,
    ) -> None:
        """Update real_max_page + total_upwork_jobs from paging payload.

        Priority:
        1) filter_total (sum of Experience level buckets) — authoritative.
        2) paging.total — only allowed to raise the known limit.
        """
        filter_total = paging.get("filter_total", 0)
        paging_total = paging.get("total", 0)
        existing_real_max = cat_state.get("real_max_page", 0)

        if filter_total > 0:
            real_max = min(100, math.ceil(filter_total / PER_PAGE))
            cat_state["total_upwork_jobs"] = filter_total
            if existing_real_max != real_max:
                cat_state["real_max_page"] = real_max
                log.info(
                    "   📏 [%s] real_max_page=%d (filter_total=%d, %s)",
                    cat_name,
                    real_max,
                    filter_total,
                    source,
                )
        elif paging_total > 0:
            # Single-page paging.total can be context-sensitive; only raise.
            real_max = min(100, math.ceil(paging_total / PER_PAGE))
            if real_max > existing_real_max:
                cat_state["real_max_page"] = real_max
                cat_state["total_upwork_jobs"] = paging_total
                log.info(
                    "   📏 [%s] real_max_page=%d (paging_total=%d, raised, %s)",
                    cat_name,
                    real_max,
                    paging_total,
                    source,
                )

    # ── Load state ────────────────────────────────────────────────────
    state = load_state()
    if args.reset:
        log.info("🔄 State reset requested — starting fresh")

    # ── Normalize state keys + reset session defaults ──────────────────
    # Requirement for manual chaos start:
    # - total_upwork_jobs = 0
    # - real_max_page = 0
    # - visited_pages = []
    # - collected = 0
    # for all 12 categories before prepass/weighted collection begins.
    for _, uid in all_cats:
        cat_st = state.setdefault(uid, {"collected": 0, "visited_pages": []})
        cat_st["collected"] = 0
        cat_st["visited_pages"] = []
        cat_st["real_max_page"] = 0
        cat_st["total_upwork_jobs"] = 0

    # Persist zeroed totals so UI/API shows a clean baseline immediately.
    save_state(state)
    log.info(
        "📊 Chaos state loaded: %d categories tracked",
        len(state),
    )
    for name, uid in all_cats:
        s = state.get(uid, {"collected": 0, "visited_pages": []})
        log.info(
            "   %-38s collected=%d  visited_pages=%s",
            name,
            s["collected"],
            s["visited_pages"][:10],
        )

    # ── DB setup ──────────────────────────────────────────────────────
    db: ScraperPostgresService | None = None
    if db_url:
        try:
            db = ScraperPostgresService(db_url)
            log.info("✅ DB connected")
        except Exception as exc:
            log.error("DB connection failed: %s — continuing without DB", exc)
            db = None
    else:
        log.warning("DATABASE_URL not set — results will NOT be saved to DB")

    # ── Pre-load known UIDs per category into memory ──────────────────
    # This lets us detect duplicates instantly (before INSERT)
    # instead of learning about them only from ON CONFLICT rowcount.
    known_uids: dict[str, set[str]] = {}
    if db is not None:
        log.info("📥 Loading known job UIDs from DB (dedup cache)...")
        for _, cat_uid in all_cats:
            try:
                uid_set = db.fetch_known_uids(cat_uid)
                known_uids[cat_uid] = uid_set
                log.info(
                    "   %-20s  known_uids=%d", cat_uid, len(uid_set)
                )
            except Exception as exc:
                log.warning(
                    "Could not load known UIDs for %s: %s",
                    cat_uid, exc,
                )
                known_uids[cat_uid] = set()
    else:
        for _, cat_uid in all_cats:
            known_uids[cat_uid] = set()

    # ── Browser ───────────────────────────────────────────────────────
    service = UpworkScraperService(
        page_delay_min=float(args.delay_min),
        page_delay_max=float(args.delay_max),
        user_data_dir=user_data_dir,
        proxy_url=proxy_url,
    )
    await service.start_browser()

    # ── One-time totals prepass (all 12 categories, random order) ─────
    # Before weighted job collection, refresh total_upwork_jobs/real_max_page
    # by probing page 1 and reading Experience-level derived totals.
    prepass_order = all_cats[:]
    random.shuffle(prepass_order)
    log.info("🧭 Totals prepass started (all categories, random order)")
    for idx, (cat_name, cat_uid) in enumerate(prepass_order, start=1):
        if not time_ok():
            log.warning("⏱️  Totals prepass stopped by time limit")
            break

        cat_state = state.setdefault(
            cat_uid, {"collected": 0, "visited_pages": [], "total_upwork_jobs": 0}
        )
        log.info("   🧮 [%s] prepass %d/%d ...", cat_name, idx, len(prepass_order))
        try:
            _, pre_paging = await service.scrape_page_with_paging(
                category_uid=cat_uid,
                page=1,
            )
            apply_paging_totals(
                cat_state,
                cat_name,
                pre_paging,
                source="session prepass",
            )
        except Exception as exc:
            log.warning("   ⚠️  [%s] prepass failed: %s", cat_name, exc)
        finally:
            save_state(state)

    total_inserted_session = 0
    total_pages_session = 0
    session_run_ids: dict[str, int] = {}

    try:
        # ── Main chaos loop ───────────────────────────────────────────
        while time_ok():
            # Filter categories that haven't reached target
            active_cats = [
                (name, uid)
                for name, uid in all_cats
                if state.get(uid, {}).get("collected", 0) < args.target_per_cat
            ]

            if not active_cats:
                log.info(
                    "🎯 All categories reached target of %d jobs — done!",
                    args.target_per_cat,
                )
                break

            # Weighted random order: categories with fewer collected jobs
            # get proportionally more chances to be picked first.
            # Weight = sqrt(target - collected) so deficit drives priority
            # but doesn't completely starve already-progressed categories.
            import math as _math
            cat_weights = []
            for cat_name_w, cat_uid_w in active_cats:
                collected = state.get(cat_uid_w, {}).get("collected", 0)
                deficit = max(1, args.target_per_cat - collected)
                cat_weights.append(_math.sqrt(deficit))

            # Build visit order by sampling without replacement using weights
            remaining = list(range(len(active_cats)))
            visit_order = []
            remaining_weights = list(cat_weights)
            while remaining:
                chosen_idx = random.choices(
                    remaining, weights=remaining_weights, k=1
                )[0]
                pos = remaining.index(chosen_idx)
                visit_order.append(active_cats[chosen_idx])
                remaining.pop(pos)
                remaining_weights.pop(pos)

            session_made_progress = False

            for cat_name, cat_uid in visit_order:
                if not time_ok():
                    break

                cat_state = state.setdefault(
                    cat_uid, {"collected": 0, "visited_pages": []}
                )

                if cat_state["collected"] >= args.target_per_cat:
                    continue

                # ── Pick a random page we haven't visited yet ─────────
                visited = set(cat_state["visited_pages"])
                # Use real max page discovered from paging data, or 100 cap.
                # real_max_page is stored in state after first fetch.
                # NOTE: real_max_page=0 means "unknown yet", not "zero pages".
                max_possible = min(
                    100,
                    cat_state.get("real_max_page") or 100,
                )
                all_possible = [
                    p for p in range(1, max_possible + 1)
                    if p not in visited
                ]
                if not all_possible:
                    log.info(
                        "  [%s] All %d pages visited — skipping",
                        cat_name, max_possible,
                    )
                    continue

                # Weighted choice: pages 1–15 get 3× weight (most jobs there)
                # Pages 16–50 get 1× weight, pages 51+ get 0.3× weight
                weights = []
                for p in all_possible:
                    if p <= 15:
                        weights.append(3.0)
                    elif p <= 50:
                        weights.append(1.0)
                    else:
                        weights.append(0.3)

                # Pick N random pages for this category this iteration
                n_pages = min(args.max_pages_per_cat, len(all_possible))
                chosen_pages = random.choices(
                    all_possible, weights=weights, k=n_pages * 3
                )
                # Deduplicate while preserving order
                seen: set[int] = set()
                unique_pages: list[int] = []
                for p in chosen_pages:
                    if p not in seen:
                        seen.add(p)
                        unique_pages.append(p)
                    if len(unique_pages) >= n_pages:
                        break

                log.info(
                    "🎲 [%s] collected=%d/%d  pages to visit: %s",
                    cat_name,
                    cat_state["collected"],
                    args.target_per_cat,
                    unique_pages,
                )

                # Ensure DB run record
                run_id: int | None = session_run_ids.get(cat_uid)
                if run_id is None and db is not None:
                    try:
                        run_id = db.start_scrape_run(
                            category_uid=cat_uid,
                            category_name=cat_name,
                        )
                        session_run_ids[cat_uid] = run_id
                    except Exception as exc:
                        log.error("DB start_scrape_run failed: %s", exc)
                        run_id = None

                # ── Scrape chosen pages in batches of 2 ──────────────
                # Within a batch: no delay between pages (back-to-back).
                # Between batches: normal random delay.
                # This doubles throughput: 100 jobs per "step" instead of 50.
                BATCH_SIZE = 2
                page_batches = [
                    unique_pages[i:i + BATCH_SIZE]
                    for i in range(0, len(unique_pages), BATCH_SIZE)
                ]
                total_steps = len(page_batches) + 1  # include pre-step 0

                # ── Pre-step: refresh true category total (batch 0/N) ──────
                # Before collecting jobs, hit page 1 once to refresh
                # Experience-level derived totals (filter_total). This keeps
                # chaos-state Upwork totals accurate for UI and planning.
                if time_ok() and cat_state["collected"] < args.target_per_cat:
                    log.info(
                        "   🧮 [%s] batch 0/%d: refresh category total...",
                        cat_name,
                        total_steps,
                    )
                    try:
                        _, pre_paging = await service.scrape_page_with_paging(
                            category_uid=cat_uid,
                            page=1,
                        )
                        apply_paging_totals(
                            cat_state,
                            cat_name,
                            pre_paging,
                            source="pre-step",
                        )
                        save_state(state)
                    except Exception as exc:
                        log.warning(
                            "   ⚠️  [%s] batch 0/%d failed: %s",
                            cat_name,
                            total_steps,
                            exc,
                        )

                for batch_idx, batch in enumerate(page_batches):
                    if not time_ok():
                        break

                    if cat_state["collected"] >= args.target_per_cat:
                        break

                    batch_jobs: list[dict] = []

                    for page_num in batch:
                        if not time_ok():
                            break

                        # Skip pages beyond real_max_page
                        real_max_now = cat_state.get("real_max_page", 0)
                        if real_max_now and page_num > real_max_now:
                            log.info(
                                "   ⏭ [%s] page %d > real_max=%d — skip",
                                cat_name, page_num, real_max_now,
                            )
                            cat_state["visited_pages"].append(page_num)
                            continue

                        log.info(
                            "   📄 [%s] page %d (batch %d/%d) ...",
                            cat_name, page_num,
                            batch_idx + 1, total_steps,
                        )

                        try:
                            page_jobs, paging = (
                                await service.scrape_page_with_paging(
                                    category_uid=cat_uid,
                                    page=page_num,
                                )
                            )
                        except Exception as exc:
                            log.warning(
                                "   ⚠️  [%s] page %d failed: %s",
                                cat_name, page_num, exc,
                            )
                            cat_state["visited_pages"].append(page_num)
                            save_state(state)
                            continue

                        # None = load error, not empty page
                        if page_jobs is None:
                            log.warning(
                                "   ⚠️  [%s] page %d load failed — skip",
                                cat_name, page_num,
                            )
                            cat_state["visited_pages"].append(page_num)
                            save_state(state)
                            continue

                        apply_paging_totals(
                            cat_state,
                            cat_name,
                            paging,
                            source=f"page {page_num}",
                        )

                        cat_state["visited_pages"].append(page_num)

                        # Empty page = beyond category limit
                        if not page_jobs:
                            cur_real_max = cat_state.get(
                                "real_max_page", 0
                            )
                            log.info(
                                "   ⚪ [%s] page %d empty — "
                                "Upwork limit (real_max=%s)",
                                cat_name, page_num,
                                cur_real_max or "unknown",
                            )
                            mark_up_to = cur_real_max or max_possible
                            visited_set = set(cat_state["visited_pages"])
                            for future_p in range(
                                page_num, mark_up_to + 1
                            ):
                                if future_p not in visited_set:
                                    cat_state["visited_pages"].append(
                                        future_p
                                    )
                            save_state(state)
                            break

                        # Pre-check duplicates using in-memory set
                        cat_known = known_uids.get(cat_uid, set())
                        new_in_page = [
                            j for j in page_jobs
                            if (j.get("uid") or j.get("ciphertext"))
                            not in cat_known
                        ]
                        log.info(
                            "   🔍 [%s] page %d: %d jobs, "
                            "%d new (pre-filter), %d known dups",
                            cat_name, page_num,
                            len(page_jobs),
                            len(new_in_page),
                            len(page_jobs) - len(new_in_page),
                        )

                        batch_jobs.extend(page_jobs)

                        # ── Intra-batch human-like pause ──────────────
                        # Between pages inside a batch: short random delay
                        # (3–9 s) that mimics a user glancing at results
                        # before clicking "Next page". Much shorter than
                        # the inter-batch delay but not zero — avoids
                        # back-to-back requests that look bot-like.
                        is_last_in_batch = (
                            page_num == batch[-1]
                        )
                        if not is_last_in_batch and time_ok():
                            intra_delay = random.uniform(3.0, 9.0)
                            log.info(
                                "   ⏸  Intra-batch pause %.1fs ...",
                                intra_delay,
                            )
                            await __import__("asyncio").sleep(
                                intra_delay
                            )

                    # ── Insert entire batch at once ───────────────────
                    if batch_jobs and db is not None and run_id is not None:
                        try:
                            inserted, dups = db.insert_raw_jobs(
                                jobs=batch_jobs,
                                scrape_run_id=run_id,
                                category_uid=cat_uid,
                                category_name=cat_name,
                                known_uids=known_uids.get(cat_uid),
                            )
                        except Exception as exc:
                            log.error(
                                "DB insert_raw_jobs failed: %s", exc
                            )
                            inserted, dups = 0, 0
                    else:
                        inserted, dups = 0, 0

                    cat_state["collected"] += inserted
                    total_inserted_session += inserted
                    total_pages_session += len(batch)
                    if inserted > 0:
                        session_made_progress = True

                    log.info(
                        "   ✅ [%s] batch %d/%d: +%d new jobs, "
                        "%d dups (total=%d/%d)",
                        cat_name, batch_idx + 1, total_steps,
                        inserted, dups,
                        cat_state["collected"], args.target_per_cat,
                    )

                    save_state(state)

                    # Delay between batches (not within a batch)
                    is_last_batch = batch_idx == len(page_batches) - 1
                    if time_ok() and not is_last_batch:
                        delay = random.randint(
                            args.delay_min, args.delay_max
                        )
                        log.info(
                            "   ⏳ Waiting %ds before next batch...",
                            delay,
                        )
                        await __import__("asyncio").sleep(delay)

            if not session_made_progress:
                log.info(
                    "No progress made in this iteration — "
                    "all categories either complete or at Upwork limit"
                )
                break

        # ── Finish DB run records ─────────────────────────────────────
        if db is not None:
            for cat_uid, run_id in session_run_ids.items():
                cat_state = state.get(cat_uid, {})
                try:
                    db.finish_scrape_run(
                        run_id=run_id,
                        pages_collected=len(
                            cat_state.get("visited_pages", [])),
                        jobs_collected=cat_state.get("collected", 0),
                        jobs_inserted=cat_state.get("collected", 0),
                        jobs_skipped=0,
                        status="done",
                    )
                except Exception as exc:
                    log.error(
                        "DB finish_scrape_run failed for %s: %s",
                        cat_uid, exc,
                    )

    except Exception as exc:
        log.error("Chaos scraper error: %s", exc, exc_info=True)

    finally:
        await service.stop_browser()
        if db is not None:
            db.close()

    # ── Final summary ─────────────────────────────────────────────────
    log.info("═" * 60)
    log.info(
        "🏁 Chaos session complete — %ds elapsed",
        int(elapsed_seconds()),
    )
    log.info(
        "   Pages scraped  : %d", total_pages_session
    )
    log.info(
        "   Jobs inserted  : %d", total_inserted_session
    )
    log.info("   Category progress:")
    for name, uid in all_cats:
        s = state.get(uid, {"collected": 0})
        done = "✅" if s["collected"] >= args.target_per_cat else "⏳"
        log.info(
            "   %s %-38s %d/%d",
            done, name, s["collected"], args.target_per_cat,
        )
    log.info("═" * 60)

    # Reset table for next session start/stop/finish UX in Grafana.
    for _, uid in all_cats:
        state[uid] = {
            "collected": 0,
            "visited_pages": [],
            "real_max_page": 0,
            "total_upwork_jobs": 0,
        }
    save_state(state)
    log.info("🧹 Chaos state reset to zero baseline for next session.")


async def _cmd_warmup(args: argparse.Namespace) -> None:
    """Warm up browser session by visiting public pages."""
    import os
    import random
    from pathlib import Path

    log.info("🔥 Starting browser warmup session...")

    # Get config from args or env
    proxy_url = args.proxy_url or os.getenv("PROXY_URL")
    user_data_dir_str = args.user_data_dir or os.getenv(
        "CHROME_USER_DATA_DIR"
    )
    cookie_backup_str = args.cookie_backup or os.getenv(
        "COOKIE_BACKUP_PATH", "data/session_cookies.json"
    )

    user_data_dir = Path(user_data_dir_str) if user_data_dir_str else None
    cookie_backup = Path(cookie_backup_str)

    # Warmup URLs - mix of Upwork pages and general web
    upwork_pages = [
        "https://www.upwork.com/",
        "https://www.upwork.com/i/how-it-works/client/",
        "https://www.upwork.com/talent-marketplace/",
        "https://www.upwork.com/agencies",
        "https://www.upwork.com/business-plus",
        "https://www.upwork.com/anyhire",
        "https://www.upwork.com/contract-to-hire/client",
        "https://www.upwork.com/hire/",
        "https://www.upwork.com/i/how-it-works/freelancer/",
        "https://www.upwork.com/freelance-jobs/",
    ]

    # Add some general public sites for more natural behavior
    general_pages = [
        "https://www.wikipedia.org/",
        "https://news.ycombinator.com/",
        "https://www.reddit.com/",
    ]

    # Shuffle and pick 5-7 Upwork pages + 1-2 general pages
    random.shuffle(upwork_pages)
    random.shuffle(general_pages)
    warmup_urls = upwork_pages[:6] + general_pages[:2]
    random.shuffle(warmup_urls)  # Mix them together

    log.info("Selected %d pages for warmup", len(warmup_urls))

    # Create scraper service
    service = UpworkScraperService(
        chrome_path=os.getenv(
            "CHROME_PATH",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ),
        user_data_dir=user_data_dir,
        proxy_url=proxy_url,
        cookie_backup_path=cookie_backup,
        page_delay_min=3,
        page_delay_max=8,
    )

    try:
        # Start browser
        await service.start_browser()
        log.info("✅ Browser started successfully")

        # Visit each warmup page
        for idx, url in enumerate(warmup_urls, 1):
            log.info("📄 [%d/%d] Visiting: %s", idx, len(warmup_urls), url)

            try:
                await service.page.get(url)

                # Random delay between 3-8 seconds
                delay = random.uniform(3, 8)
                log.info("   ⏳ Waiting %.1fs...", delay)
                await asyncio.sleep(delay)

                # Simulate some scrolling on Upwork pages
                if "upwork.com" in url and random.random() > 0.5:
                    log.info("   📜 Simulating scroll...")
                    await service.page.evaluate(
                        "window.scrollTo(0, document.body.scrollHeight / 2)"
                    )
                    await asyncio.sleep(random.uniform(1, 2))

            except Exception as e:
                log.warning("   ⚠️  Failed to load %s: %s", url, e)
                continue

        log.info("🎉 Warmup complete! Session should be ready.")
        log.info(
            "   Cookies and session data saved to user-data-dir "
            "and cookie backup."
        )

    finally:
        # Stop browser and save cookies
        await service.stop_browser()


def main() -> None:
    """Dispatch CLI command."""
    args = _parse_args()

    if args.command == "scrape-categories":
        asyncio.run(_cmd_scrape_categories())
    elif args.command == "scrape":
        asyncio.run(_cmd_scrape(args))
    elif args.command == "scrape-chaos":
        asyncio.run(_cmd_scrape_chaos(args))
    elif args.command == "inspect-category":
        asyncio.run(_cmd_inspect_category(args))
    elif args.command == "warmup":
        asyncio.run(_cmd_warmup(args))
    else:
        log.error("Unknown command: %s", args.command)
        sys.exit(1)


if __name__ == "__main__":
    main()
