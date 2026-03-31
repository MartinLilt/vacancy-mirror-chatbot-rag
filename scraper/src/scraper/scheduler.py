"""Scheduler logic for scraper — work hours, regions, timing.

Handles:
- Work hours (8:00-22:00 by IP region timezone)
- Work days (Monday-Saturday, rest on Sunday)
- Random start times to emulate human behavior
- Level detection (1: 2500, 2: 5000, 3: 5-25k, 4: 25k+)
"""

from __future__ import annotations

import logging
import random
from datetime import datetime

log = logging.getLogger(__name__)


def should_run_today() -> bool:
    """Check if scraper should run today (Monday-Saturday).

    Returns:
        bool: True if today is Mon-Sat, False if Sunday.
    """
    weekday = datetime.now().weekday()  # 0=Mon, 6=Sun
    is_workday = weekday in [0, 1, 2, 3, 4, 5]
    log.info(
        f"Today: {_weekday_name(weekday)} (weekday={weekday}), "
        f"workday={is_workday}"
    )
    return is_workday


def is_work_hours(start_hour: int = 8, end_hour: int = 22) -> bool:
    """Check if current time is within work hours.

    Args:
        start_hour: Start hour (default 8 = 8:00 AM).
        end_hour: End hour (default 22 = 10:00 PM).

    Returns:
        bool: True if now is between start_hour and end_hour.
    """
    now = datetime.now()
    current_hour = now.hour
    is_within = start_hour <= current_hour < end_hour
    log.info(
        f"Current time: {now.strftime('%H:%M:%S')}, "
        f"work hours: {start_hour}:00-{end_hour}:00, "
        f"within={is_within}"
    )
    return is_within


def get_random_delay(min_sec: int = 30, max_sec: int = 45) -> int:
    """Generate random delay between page scrapes.

    Args:
        min_sec: Minimum delay in seconds.
        max_sec: Maximum delay in seconds.

    Returns:
        int: Random delay in seconds.
    """
    delay = random.randint(min_sec, max_sec)
    log.debug(f"Random delay: {delay} sec (range {min_sec}-{max_sec})")
    return delay


def detect_level(total_jobs: int) -> int:
    """Detect scraper level based on total job count.

    Levels:
        1: 0-2500 jobs
        2: 2501-5000 jobs
        3: 5001-25000 jobs
        4: 25001+ jobs

    Args:
        total_jobs: Total number of jobs in category.

    Returns:
        int: Level (1, 2, 3, or 4).
    """
    if total_jobs <= 2500:
        level = 1
    elif total_jobs <= 5000:
        level = 2
    elif total_jobs <= 25000:
        level = 3
    else:
        level = 4

    log.info(
        f"Detected level {level} for {total_jobs:,} jobs "
        f"(1=≤2.5k, 2=≤5k, 3=≤25k, 4=>25k)"
    )
    return level


def _weekday_name(weekday: int) -> str:
    """Convert weekday number to name.

    Args:
        weekday: 0=Monday, 6=Sunday.

    Returns:
        str: Day name.
    """
    names = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    return names[weekday]


# Future enhancement: IP-based timezone detection
# def get_timezone_by_ip() -> str:
#     """Detect timezone based on server IP geolocation.
#
#     Returns:
#         str: Timezone name (e.g., 'Europe/Berlin').
#     """
#     # TODO: Use IP geolocation API
#     # For now, assume Europe/Berlin
#     return "Europe/Berlin"
