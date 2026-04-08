"""Helpers for keeping chaos paging bounds realistic."""

from __future__ import annotations

import math


def bounded_real_max_from_paging(
    *,
    paging_total: int,
    existing_real_max: int,
    per_page: int,
    max_allowed_page: int = 100,
    shrink_gap_pages: int = 10,
    shrink_safety_pages: int = 2,
) -> tuple[int, str]:
    """Return bounded real max page and decision label.

    Decision labels:
    - ``init``: no previous bound, initialize from observed total
    - ``raised``: observed total increases the known bound
    - ``shrunk``: previous bound is clearly stale and was reduced
    - ``kept``: keep previous bound
    """
    if paging_total <= 0:
        return max(0, int(existing_real_max)), "kept"

    observed_max = min(
        max_allowed_page,
        max(1, math.ceil(paging_total / max(1, per_page))),
    )
    existing = max(0, int(existing_real_max))

    if existing == 0:
        return observed_max, "init"
    if observed_max > existing:
        return observed_max, "raised"

    # Shrink only when the mismatch is large enough to avoid oscillation.
    if (existing - observed_max) >= max(1, shrink_gap_pages):
        shrunk = min(existing, observed_max + max(0, shrink_safety_pages))
        return max(1, shrunk), "shrunk"

    return existing, "kept"

