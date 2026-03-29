"""Display scraper load level for each Upwork category.

Reads ``scripts/upwork_category_uids.json`` (produced by
``scrape_category_uids.py``) and prints a formatted table showing each
category's total job count and its assigned scraper load level.

Usage::

    python scripts/show_category_load.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow imports from src/ without installing the package.
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "src"),
)

from vacancy_mirror_chatbot_rag.categories import (  # noqa: E402
    CategoryLoad,
    classify_load,
)

_LEVEL_DESCRIPTIONS: dict[int, str] = {
    1: "max_pages=50  (≤2 500 jobs, single pass)",
    2: "max_pages=100 (≤5 000 jobs, single pass)",
    3: "splits needed (≤25 000 jobs, 1 scraper/week)",
    4: "splits + extra replica (>25 000 jobs, k8s scale)",
}

_LEVEL_ICONS: dict[int, str] = {
    1: "🟢",
    2: "🟡",
    3: "🟠",
    4: "🔴",
}


def main() -> None:
    """Load category data and print the load-level table."""
    json_path = (
        Path(__file__).resolve().parent / "upwork_category_uids.json"
    )
    if not json_path.exists():
        print(
            f"ERROR: {json_path} not found. "
            "Run scripts/scrape_category_uids.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    raw: dict[str, dict] = json.loads(
        json_path.read_text(encoding="utf-8")
    )

    # Only top-level categories (no is_subcategory key or False).
    categories: list[CategoryLoad] = []
    for name, info in raw.items():
        if info.get("is_subcategory"):
            continue
        total_jobs = info.get("total_jobs") or 0
        uid = info.get("uid", "")
        categories.append(classify_load(name, uid, total_jobs))

    # Sort by level then total_jobs descending.
    categories.sort(key=lambda c: (c.level, -c.total_jobs))

    # Print table.
    header = (
        f"{'#':>2}  {'Lvl':>3}  {'Icon':>4}  "
        f"{'Total jobs':>10}  "
        f"{'max_pages':>9}  "
        f"{'Splits':>6}  "
        f"{'+Replica':>8}  "
        f"Category"
    )
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)

    for i, cat in enumerate(categories, start=1):
        icon = _LEVEL_ICONS[cat.level]
        print(
            f"{i:>2}  "
            f"L{cat.level:>1}   "
            f"{icon}   "
            f"{cat.total_jobs:>10,}  "
            f"{cat.max_pages:>9}  "
            f"{'yes' if cat.needs_splits else 'no':>6}  "
            f"{'yes' if cat.needs_extra_replica else 'no':>8}  "
            f"{cat.name}"
        )

    print(sep)

    # Summary per level.
    print("\n=== Summary by level ===\n")
    for lvl in range(1, 5):
        group = [c for c in categories if c.level == lvl]
        if not group:
            continue
        icon = _LEVEL_ICONS[lvl]
        desc = _LEVEL_DESCRIPTIONS[lvl]
        total = sum(c.total_jobs for c in group)
        names = ", ".join(c.name for c in group)
        print(
            f"  {icon} Level {lvl} — {desc}\n"
            f"     Categories ({len(group)}): {names}\n"
            f"     Total jobs across group: {total:,}\n"
        )


if __name__ == "__main__":
    main()
