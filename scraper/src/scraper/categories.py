"""Upwork job category definitions for search URL construction.

Category UIDs were collected by running scripts/scrape_category_uids.py
against live Upwork search filters on 2026-03-26.

Note: Upwork uses a single ``category2_uid`` per parent category.
All subcategories listed under a parent share that parent's UID,
so filtering is done at the parent-category level.

Scraper load levels
-------------------
Each category is classified into one of four scraper load levels based
on ``total_jobs`` reported by Upwork.  Upwork hard-caps pagination at
100 pages × 50 results = 5 000 jobs per plain category URL.  Categories
with more than 5 000 jobs require filter-based URL splitting (e.g. by
``hourly_rate`` range) so that each split covers ≤ 5 000 jobs.

Level 1 — ≤ 2 500 jobs
    Single scraper pass, ``max_pages=50``.  Completes in < 30 min.

Level 2 — 2 501–5 000 jobs
    Single scraper pass, ``max_pages=100``.  Completes in < 60 min.

Level 3 — 5 001–25 000 jobs
    Requires URL filter splits.  One scraper instance can cover the full
    volume within one week (≤ 17 300 pages/week at ~35 s/page × 7 days).

Level 4 — > 25 000 jobs
    Requires URL filter splits AND a second parallel scraper container
    (Kubernetes HPA / manual replica) to cover the volume in one week.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# ---------------------------------------------------------------------------
# Scraper load level type
# ---------------------------------------------------------------------------

LoadLevel = Literal[1, 2, 3, 4]

#: Boundaries (inclusive upper bound) for each scraper load level.
#: Level 4 has no upper bound.
_LEVEL_THRESHOLDS: list[tuple[int, LoadLevel]] = [
    (2_500, 1),
    (5_000, 2),
    (25_000, 3),
]


@dataclass(frozen=True)
class CategoryLoad:
    """Scraper load classification for a single category.

    Attributes:
        name: Category display name.
        uid: Upwork ``category2_uid`` value.
        total_jobs: Total vacancies reported by Upwork.
        level: Scraper load level (1–4).
        max_pages: Recommended ``max_pages`` for the scraper.
        needs_splits: Whether URL filter splits are required.
        needs_extra_replica: Whether a second scraper container
            is needed to cover the volume within one week.
    """

    name: str
    uid: str
    total_jobs: int
    level: LoadLevel
    max_pages: int
    needs_splits: bool
    needs_extra_replica: bool


def classify_load(
    name: str,
    uid: str,
    total_jobs: int,
) -> CategoryLoad:
    """Classify a category into a scraper load level.

    Args:
        name: Category display name.
        uid: Upwork ``category2_uid`` value.
        total_jobs: Total vacancies reported by Upwork.

    Returns:
        A :class:`CategoryLoad` dataclass with all derived fields set.
    """
    level: LoadLevel = 4
    for threshold, lvl in _LEVEL_THRESHOLDS:
        if total_jobs <= threshold:
            level = lvl
            break

    max_pages = 50 if level == 1 else 100
    needs_splits = level >= 3
    needs_extra_replica = level == 4
    return CategoryLoad(
        name=name,
        uid=uid,
        total_jobs=total_jobs,
        level=level,
        max_pages=max_pages,
        needs_splits=needs_splits,
        needs_extra_replica=needs_extra_replica,
    )


# ---------------------------------------------------------------------------
# Category UID registry
# ---------------------------------------------------------------------------

# Mapping of parent category display name → category2_uid.
# Use these UIDs to build search URLs:
#   https://www.upwork.com/nx/search/jobs/
#       ?category2_uid=<uid>&per_page=50&page=1
CATEGORY_UIDS: dict[str, str] = {
    "Accounting & Consulting": "531770282584862721",
    "Admin Support": "531770282580668416",
    "Customer Service": "531770282580668417",
    "Data Science & Analytics": "531770282580668420",
    "Design & Creative": "531770282580668421",
    "Engineering & Architecture": "531770282584862722",
    "IT & Networking": "531770282580668419",
    "Legal": "531770282584862723",
    "Sales & Marketing": "531770282580668422",
    "Translation": "531770282584862720",
    "Web, Mobile & Software Dev": "531770282580668418",
    "Writing": "531770282580668423",
}

# All Upwork job categories grouped by parent.
# Keys are parent category names (must match keys in CATEGORY_UIDS).
# Values are lists of subcategory display names.
UPWORK_CATEGORIES: dict[str, list[str]] = {
    "Accounting & Consulting": [
        "Personal & Professional Coaching",
        "Accounting & Bookkeeping",
        "Financial Planning",
        "Recruiting & Human Resources",
        "Management Consulting & Analysis",
        "Other - Accounting & Consulting",
    ],
    "Admin Support": [
        "Data Entry & Transcription Services",
        "Virtual Assistance",
        "Project Management",
        "Market Research & Product Reviews",
    ],
    "Customer Service": [
        "Community Management & Tagging",
        "Customer Service & Tech Support",
    ],
    "Data Science & Analytics": [
        "Data Analysis & Testing",
        "Data Extraction/ETL",
        "Data Mining & Management",
        "AI & Machine Learning",
    ],
    "Design & Creative": [
        "Art & Illustration",
        "Audio & Music Production",
        "Branding & Logo Design",
        "NFT, AR/VR & Game Art",
        "Graphic, Editorial & Presentation Design",
        "Performing Arts",
        "Photography",
        "Product Design",
        "Video & Animation",
    ],
    "Engineering & Architecture": [
        "Building & Landscape Architecture",
        "Chemical Engineering",
        "Civil & Structural Engineering",
        "Contract Manufacturing",
        "Electrical & Electronic Engineering",
        "Interior & Trade Show Design",
        "Energy & Mechanical Engineering",
        "Physical Sciences",
        "3D Modeling & CAD",
    ],
    "IT & Networking": [
        "Database Management & Administration",
        "ERP/CRM Software",
        "Information Security & Compliance",
        "Network & System Administration",
        "DevOps & Solution Architecture",
    ],
    "Legal": [
        "Corporate & Contract Law",
        "International & Immigration Law",
        "Finance & Tax Law",
        "Public Law",
    ],
    "Sales & Marketing": [
        "Digital Marketing",
        "Lead Generation & Telemarketing",
        "Marketing, PR & Brand Strategy",
    ],
    "Translation": [
        "Language Tutoring & Interpretation",
        "Translation & Localization Services",
    ],
    "Web, Mobile & Software Dev": [
        "Blockchain, NFT & Cryptocurrency",
        "AI Apps & Integration",
        "Desktop Application Development",
        "Ecommerce Development",
        "Game Design & Development",
        "Mobile Development",
        "Other - Software Development",
        "Product Management & Scrum",
        "QA Testing",
        "Scripts & Utilities",
        "Web & Mobile Design",
        "Web Development",
    ],
    "Writing": [
        "Sales & Marketing Copywriting",
        "Content Writing",
        "Editing & Proofreading Services",
        "Professional & Business Writing",
    ],
}

# Flat list of all subcategories (leaf nodes only).
ALL_SUBCATEGORIES: list[str] = [
    sub
    for subs in UPWORK_CATEGORIES.values()
    for sub in subs
]


def get_uid(parent_category: str) -> str | None:
    """Return the category2_uid for a parent category name.

    Args:
        parent_category: Exact parent category name, e.g.
            ``"Web, Mobile & Software Dev"``.

    Returns:
        The UID string, or ``None`` if the category is unknown.
    """
    return CATEGORY_UIDS.get(parent_category)


def build_category_url(
    parent_category: str,
    *,
    page: int = 1,
    per_page: int = 50,
) -> str | None:
    """Build an Upwork search URL filtered to a specific parent category.

    Args:
        parent_category: Exact parent category name.
        page: Page number (1-based).
        per_page: Results per page (10, 20, or 50).

    Returns:
        Full search URL string, or ``None`` if category is unknown.
    """
    uid = get_uid(parent_category)
    if uid is None:
        return None
    base = "https://www.upwork.com/nx/search/jobs/"
    return (
        f"{base}?category2_uid={uid}"
        f"&per_page={per_page}&page={page}"
    )
