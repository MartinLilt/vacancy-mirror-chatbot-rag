"""Entry point for the scraper container.

Commands
--------
scrape-categories   Scrape UIDs + job counts for all top-level categories.
scrape              Scrape job listings for a specific category UID.
inspect-category    Open the Upwork dropdown, click one category, verify
                    its UID against our registry and print a load report.

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
import sys

from scraper.categories import CATEGORY_UIDS
from scraper.services.postgres import ScraperPostgresService
from scraper.services.upwork_scraper import (
    CategoryScraperService,
    UpworkScraperService,
    MAX_ALLOWED_PAGE,
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
    first_url = (
        f"https://www.upwork.com/nx/search/jobs/"
        f"?category2_uid={args.uid}&per_page=50&page=1"
    )
    await service.manual_cloudflare_pass(first_url)

    status = "failed"
    jobs: list[dict] = []
    pages_scraped = 0

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
            status=status,
        )
        db.close()

    log.info(
        "Scrape complete: %d jobs collected from %d pages.",
        len(jobs),
        pages_scraped,
    )

    # ── Print raw job list for inspection ─────────────────────────
    _print_jobs(jobs, category_name=category_name)


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


def main() -> None:
    """Dispatch CLI command."""
    args = _parse_args()

    if args.command == "scrape-categories":
        asyncio.run(_cmd_scrape_categories())
    elif args.command == "scrape":
        asyncio.run(_cmd_scrape(args))
    elif args.command == "inspect-category":
        asyncio.run(_cmd_inspect_category(args))
    else:
        log.error("Unknown command: %s", args.command)
        sys.exit(1)


if __name__ == "__main__":
    main()
