"""Run the Upwork vacancy scraper for all categories.

Scrapes job listings from Upwork by loading SSR search pages and
extracting ``window.__NUXT__.state.jobsSearch.jobs`` from each page.

Results are saved per-category to ``data/raw/<category_name>.json``.

Usage:
    python scripts/run_scraper.py
    python scripts/run_scraper.py --max-pages 5
    python scripts/run_scraper.py --no-resume
    python scripts/run_scraper.py --category "Web, Mobile & Software Dev"
    python scripts/run_scraper.py --uid 531770282580668418 --label ai_apps
    python scripts/run_scraper.py --merge-only
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Allow importing from src/ when running as a script
sys.path.insert(
    0,
    str(Path(__file__).parent.parent / "src"),
)

from scraper.categories import CATEGORY_UIDS  # noqa: E402
from scraper.services.upwork_scraper import (  # noqa: E402
    MAX_ALLOWED_PAGE,
    UpworkScraperService,
    _build_url,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)

OUTPUT_DIR = Path("data/raw")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Scrape Upwork vacancies for all categories."
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=MAX_ALLOWED_PAGE,
        metavar="N",
        help=(
            f"Max pages per category (default: {MAX_ALLOWED_PAGE}"
            f" = {MAX_ALLOWED_PAGE * 50} jobs)."
        ),
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        metavar="NAME",
        help=(
            "Scrape only this category name. "
            "E.g. \"Web, Mobile & Software Dev\""
        ),
    )
    parser.add_argument(
        "--uid",
        type=str,
        default=None,
        metavar="UID",
        help=(
            "Scrape a specific category2_uid directly. "
            "Use together with --label to name the output file."
        ),
    )
    parser.add_argument(
        "--label",
        type=str,
        default=None,
        metavar="LABEL",
        help=(
            "Output file label when using --uid "
            "(e.g. 'ai_apps'). "
            "Defaults to the UID value."
        ),
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore existing checkpoints and re-scrape from page 1.",
    )
    parser.add_argument(
        "--merge-only",
        action="store_true",
        help=(
            "Do not scrape — just merge existing checkpoint files "
            "into data/raw/ JSON files."
        ),
    )
    return parser.parse_args()


def _merge_checkpoints(
    scraper: UpworkScraperService,
    uids: dict[str, str],
    max_pages: int,
) -> None:
    """Merge checkpoint files into data/raw/ without scraping."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, uid in uids.items():
        jobs = scraper.load_all_checkpoints(uid, 1, max_pages)
        if not jobs:
            log.warning("No checkpoints found for %s, skipping.", name)
            continue
        safe_name = (
            name.lower()
            .replace(" ", "_")
            .replace("/", "_")
            .replace("&", "and")
            .replace(",", "")
        )
        out_path = OUTPUT_DIR / f"{safe_name}.json"
        import json
        out_path.write_text(
            json.dumps(jobs, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        log.info("Merged %d jobs → %s", len(jobs), out_path)


async def main() -> None:
    """Entry point."""
    args = parse_args()

    # Select categories to scrape
    if args.uid:
        label = args.label or args.uid
        uids = {label: args.uid}
    elif args.category:
        if args.category not in CATEGORY_UIDS:
            log.error(
                "Unknown category %r. Available:\n  %s",
                args.category,
                "\n  ".join(CATEGORY_UIDS.keys()),
            )
            return
        uids = {args.category: CATEGORY_UIDS[args.category]}
    else:
        uids = CATEGORY_UIDS

    scraper = UpworkScraperService()

    # Merge-only mode: no browser needed
    if args.merge_only:
        log.info("Merge-only mode: merging checkpoints into data/raw/")
        _merge_checkpoints(scraper, uids, args.max_pages)
        return

    resume = not args.no_resume

    # Check if all pages are already checkpointed (skip browser open)
    if resume:
        all_done = all(
            scraper._first_missing_page(uid, args.max_pages, 1)
            > min(args.max_pages, MAX_ALLOWED_PAGE)
            for uid in uids.values()
        )
        if all_done:
            log.info(
                "All pages already checkpointed. "
                "Merging into data/raw/ (no browser needed)."
            )
            _merge_checkpoints(scraper, uids, args.max_pages)
            return

    log.info(
        "Scraping %d categor%s, max %d pages each%s.",
        len(uids),
        "y" if len(uids) == 1 else "ies",
        args.max_pages,
        " (resume=off)" if not resume else "",
    )

    await scraper.start_browser()

    # Open first non-completed category for manual Cloudflare pass
    first_uid = next(iter(uids.values()))
    first_url = _build_url(first_uid, 1)
    await scraper.manual_cloudflare_pass(first_url)

    try:
        await scraper.scrape_all_categories(
            uids,
            max_pages_per_category=args.max_pages,
            output_dir=OUTPUT_DIR,
            resume=resume,
        )
        log.info(
            "Done. Data saved to %s/", OUTPUT_DIR
        )
    finally:
        await scraper.stop_browser()


if __name__ == "__main__":
    asyncio.run(main())
