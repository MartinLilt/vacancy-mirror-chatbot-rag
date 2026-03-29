"""Entry point for the scraper container.

Commands
--------
scrape-categories   Scrape UIDs + job counts for all top-level categories.
scrape              Scrape job listings for a specific category UID.

Usage (inside container)::

    python -m scraper.cli scrape-categories
    python -m scraper.cli scrape --uid 531770282580668418 --label webdev
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

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
        required=True,
        help="Human-readable label used for logging and DB records.",
    )
    scrape_p.add_argument(
        "--max-pages",
        type=int,
        default=MAX_ALLOWED_PAGE,
        metavar="N",
        help=f"Max pages to scrape (default: {MAX_ALLOWED_PAGE}).",
    )

    return parser.parse_args()


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
    """Scrape job listings for a single category."""
    service = UpworkScraperService()
    await service.scrape_category(
        category_uid=args.uid,
        max_pages=args.max_pages,
    )


def main() -> None:
    """Dispatch CLI command."""
    args = _parse_args()

    if args.command == "scrape-categories":
        asyncio.run(_cmd_scrape_categories())
    elif args.command == "scrape":
        asyncio.run(_cmd_scrape(args))
    else:
        log.error("Unknown command: %s", args.command)
        sys.exit(1)


if __name__ == "__main__":
    main()
