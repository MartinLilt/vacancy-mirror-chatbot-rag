"""State machine for scraper checkpoint management.

Tracks:
- Current page number
- Total pages for category
- Level (1-4)
- Week start/completion status
- Last run timestamp

Checkpoint file format (JSON):
{
    "category_uid": "531770282580668418",
    "category_name": "Web, Mobile & Software Dev",
    "level": 1,
    "total_pages": 50,
    "current_page": 20,
    "started_at": "2026-03-31",
    "last_run": "2026-03-31T15:30:00",
    "completed": false,
    "week_expired": false
}
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

# State directory (mounted volume in container)
STATE_DIR = Path("/app/data")


class ScraperState:
    """Manages scraper checkpoint state for resume capability."""

    def __init__(self, category_uid: str, category_name: str = ""):
        """Initialize state manager.

        Args:
            category_uid: Upwork category UID.
            category_name: Human-readable category name.
        """
        self.category_uid = category_uid
        self.category_name = category_name
        self.state_file = STATE_DIR / f"state_{category_uid}.json"

        # Ensure state directory exists
        STATE_DIR.mkdir(parents=True, exist_ok=True)

    def load_checkpoint(self) -> dict:
        """Load checkpoint from disk.

        Returns:
            dict: Checkpoint data, or default if file doesn't exist.
        """
        if not self.state_file.exists():
            log.info(
                f"No checkpoint found for {self.category_uid}, "
                "starting fresh"
            )
            return self._default_checkpoint()

        try:
            with open(self.state_file, encoding="utf-8") as f:
                data = json.load(f)
            log.info(
                f"Loaded checkpoint: page {data.get('current_page', 1)}"
                f"/{data.get('total_pages', '?')}"
            )
            return data
        except Exception as exc:  # noqa: BLE001
            log.error(f"Failed to load checkpoint: {exc}")
            return self._default_checkpoint()

    def save_checkpoint(
        self,
        current_page: int,
        total_pages: int,
        level: int,
        completed: bool = False,
    ) -> None:
        """Save checkpoint to disk.

        Args:
            current_page: Last successfully scraped page.
            total_pages: Total pages for this category.
            level: Scraper level (1-4).
            completed: Whether scraping is fully complete.
        """
        checkpoint = self.load_checkpoint()
        checkpoint.update(
            {
                "category_uid": self.category_uid,
                "category_name": self.category_name,
                "level": level,
                "total_pages": total_pages,
                "current_page": current_page,
                "last_run": datetime.now().isoformat(),
                "completed": completed,
            }
        )

        # Set started_at only on first run
        if "started_at" not in checkpoint:
            checkpoint["started_at"] = datetime.now().date().isoformat()

        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(checkpoint, f, indent=2)
            log.info(
                f"Checkpoint saved: page {current_page}/{total_pages}"
            )
        except Exception as exc:  # noqa: BLE001
            log.error(f"Failed to save checkpoint: {exc}")

    def reset_for_new_week(self) -> None:
        """Reset state for a new week (Monday).

        Clears checkpoint file to start fresh.
        """
        if self.state_file.exists():
            self.state_file.unlink()
            log.info(f"Reset state for new week: {self.category_uid}")
        else:
            log.info("No state to reset (already clean)")

    def is_week_expired(self) -> bool:
        """Check if week has expired (Saturday passed, incomplete).

        Returns:
            bool: True if it's Sunday and scraping is incomplete.
        """
        checkpoint = self.load_checkpoint()
        today = datetime.now().weekday()  # 0=Mon, 6=Sun

        # Sunday (6) and not completed
        if today == 6 and not checkpoint.get("completed", False):
            log.warning(
                "Week expired: Sunday reached but scraping incomplete"
            )
            return True

        return False

    def mark_week_expired(self) -> None:
        """Mark current week as expired (won't resume)."""
        checkpoint = self.load_checkpoint()
        checkpoint["week_expired"] = True
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(checkpoint, f, indent=2)
            log.info("Marked week as expired")
        except Exception as exc:  # noqa: BLE001
            log.error(f"Failed to mark week expired: {exc}")

    def _default_checkpoint(self) -> dict:
        """Return default empty checkpoint.

        Returns:
            dict: Default checkpoint structure.
        """
        return {
            "category_uid": self.category_uid,
            "category_name": self.category_name,
            "level": 1,
            "total_pages": 0,
            "current_page": 1,
            "started_at": datetime.now().date().isoformat(),
            "last_run": None,
            "completed": False,
            "week_expired": False,
        }
