"""Entry point: scrape Upwork category UIDs and total job counts.

Delegates all logic to
``scraper.services.upwork_scraper.CategoryScraperService``.
Results are saved to ``scripts/upwork_category_uids.json`` in the format::

    {
        "Web, Mobile & Software Dev": {
            "uid": "531770282580668418",
            "total_jobs": 48320
        },
        ...
    }
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import nodriver as uc

# Allow running from the repo root without installing the package.
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "src"),
)

from scraper.services.upwork_scraper import (  # noqa: E402
    CategoryScraperService,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

OUTPUT_FILE = Path(__file__).parent / "upwork_category_uids.json"


async def main() -> None:
    """Run the category scraper and save results to JSON."""
    svc = CategoryScraperService()
    await svc.start_browser()
    try:
        await svc.manual_cloudflare_pass()
        categories = await svc.scrape_categories()
    finally:
        await svc.stop_browser()

    log.info("Collected %d categories.", len(categories))
    OUTPUT_FILE.write_text(
        json.dumps(categories, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("Saved → %s", OUTPUT_FILE)


if __name__ == "__main__":
    uc.loop().run_until_complete(main())
