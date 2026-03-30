"""PostgreSQL write-only client for the scraper container.

The scraper only needs to insert raw vacancy data and record scrape
runs.  All read, normalization and analytics operations live in the
backend package.

Classes:
- ``ScraperPostgresService`` — insert raw jobs and scrape run records.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
from psycopg2.extras import execute_values

log = logging.getLogger(__name__)


def _safe_float(value: Any) -> float | None:
    """Convert a value to float, returning None on failure."""
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    """Convert a value to int, returning None on failure."""
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _extract_row(
    job: dict[str, Any],
    scrape_run_id: int,
    category_uid: str,
    category_name: str,
) -> tuple[Any, ...] | None:
    """Map a raw Upwork job dict to a ``raw_jobs`` INSERT row tuple.

    Kept fields (matching user spec):
    - title, description, published_at, job_type, duration_label
    - client (country, payment_verified, total_spent,
               total_reviews, total_feedback)
    - enterprise_job (bool)
    - skills (attrs[].prefLabel → TEXT[])
    - hourly_budget_min, hourly_budget_max
    - weekly_budget

    Returns None if the job has no usable uid.
    """
    job_uid = job.get("uid") or job.get("ciphertext")
    if not job_uid:
        return None

    title: str = job.get("title", "")
    description: str | None = job.get("description")
    published_at: str | None = job.get("publishedOn")

    # type: 1 = fixed, 2 = hourly
    job_type: int | None = _safe_int(job.get("type"))

    duration_label: str | None = job.get("durationLabel")

    # client block
    client: dict[str, Any] = job.get("client") or {}
    loc = client.get("location") or {}
    client_country: str | None = (
        loc.get("country") if isinstance(loc, dict) else None
    )
    client_payment_verified: bool | None = client.get(
        "isPaymentVerified"
    )
    client_total_spent = _safe_float(client.get("totalSpent"))
    client_total_reviews = _safe_int(client.get("totalReviews"))
    client_total_feedback = _safe_float(
        client.get("totalFeedback")
    )

    enterprise_job: bool = bool(job.get("enterpriseJob"))

    # skills: attrs[].prefLabel → TEXT[]
    attrs = job.get("attrs") or []
    skills: list[str] = [
        a["prefLabel"]
        for a in attrs
        if isinstance(a, dict) and a.get("prefLabel")
    ]

    # hourlyBudget
    hourly: dict[str, Any] = job.get("hourlyBudget") or {}
    hourly_min = _safe_float(hourly.get("min"))
    hourly_max = _safe_float(hourly.get("max"))

    # weeklyBudget
    weekly: dict[str, Any] = job.get("weeklyBudget") or {}
    weekly_budget = _safe_float(weekly.get("amount"))

    return (
        scrape_run_id,
        category_uid,
        category_name,
        str(job_uid),
        title,
        description,
        published_at,
        job_type,
        duration_label,
        client_country,
        client_payment_verified,
        client_total_spent,
        client_total_reviews,
        client_total_feedback,
        enterprise_job,
        skills,
        hourly_min,
        hourly_max,
        weekly_budget,
    )


class ScraperPostgresService:
    """Write-only PostgreSQL client for the scraper.

    Attributes:
        conn: The active psycopg2 connection.
    """

    def __init__(self, db_url: str) -> None:
        """Connect to PostgreSQL.

        Args:
            db_url: Full connection string, e.g.
                ``postgresql://user:pass@host:5432/dbname``.
        """
        self.conn = psycopg2.connect(db_url)
        self.conn.autocommit = False
        log.info("ScraperPostgresService connected.")

    def close(self) -> None:
        """Close the database connection."""
        if self.conn and not self.conn.closed:
            self.conn.close()
            log.info("ScraperPostgresService connection closed.")

    # ------------------------------------------------------------------
    # Scrape run lifecycle
    # ------------------------------------------------------------------

    def start_scrape_run(
        self,
        category_uid: str,
        category_name: str,
    ) -> int:
        """Insert a new scrape_run record with status 'running'.

        Args:
            category_uid: The Upwork category2_uid being scraped.
            category_name: Human-readable category name.

        Returns:
            The new scrape_run ``id``.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scrape_runs
                    (category_uid, category_name, status, started_at)
                VALUES (%s, %s, 'running', NOW())
                RETURNING id
                """,
                (category_uid, category_name),
            )
            run_id: int = cur.fetchone()[0]
        self.conn.commit()
        log.info(
            "Scrape run %d started for category '%s'.",
            run_id,
            category_name,
        )
        return run_id

    def finish_scrape_run(
        self,
        run_id: int,
        pages_collected: int,
        jobs_collected: int,
        status: str = "done",
        error_message: str | None = None,
    ) -> None:
        """Mark a scrape_run as finished.

        Args:
            run_id: The scrape_run id to update.
            pages_collected: Number of pages fetched.
            jobs_collected: Number of job rows inserted.
            status: Final status string (``"done"`` or ``"failed"``).
            error_message: Optional error detail for failed runs.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE scrape_runs
                SET status           = %s,
                    finished_at      = NOW(),
                    pages_collected  = %s,
                    jobs_collected   = %s,
                    error_message    = %s
                WHERE id = %s
                """,
                (
                    status,
                    pages_collected,
                    jobs_collected,
                    error_message,
                    run_id,
                ),
            )
        self.conn.commit()
        log.info(
            "Scrape run %d finished: status=%s, "
            "pages=%d, jobs=%d.",
            run_id,
            status,
            pages_collected,
            jobs_collected,
        )

    # ------------------------------------------------------------------
    # Raw job insertion
    # ------------------------------------------------------------------

    def insert_raw_jobs(
        self,
        jobs: list[dict[str, Any]],
        scrape_run_id: int,
        category_uid: str,
        category_name: str,
    ) -> int:
        """Bulk-insert raw job dicts into the ``raw_jobs`` table.

        Skips jobs whose ``job_uid`` already exists for this category
        (``ON CONFLICT (category_uid, job_uid) DO NOTHING``).

        Args:
            jobs: List of raw job dicts from the scraper.
            scrape_run_id: The associated scrape_run id.
            category_uid: The category2_uid these jobs belong to.
            category_name: Human-readable category name.

        Returns:
            Number of rows actually inserted (duplicates excluded).
        """
        if not jobs:
            return 0

        rows: list[tuple[Any, ...]] = []
        for job in jobs:
            row = _extract_row(
                job, scrape_run_id, category_uid, category_name
            )
            if row is not None:
                rows.append(row)

        if not rows:
            log.warning("No extractable rows from %d jobs.", len(jobs))
            return 0

        with self.conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO raw_jobs (
                    scrape_run_id,
                    category_uid,
                    category_name,
                    job_uid,
                    title,
                    description,
                    published_at,
                    job_type,
                    duration_label,
                    client_country,
                    client_payment_verified,
                    client_total_spent,
                    client_total_reviews,
                    client_total_feedback,
                    enterprise_job,
                    skills,
                    hourly_budget_min,
                    hourly_budget_max,
                    weekly_budget
                ) VALUES %s
                ON CONFLICT (category_uid, job_uid) DO NOTHING
                """,
                rows,
            )
            inserted: int = cur.rowcount
        self.conn.commit()
        log.info(
            "Inserted %d/%d raw jobs "
            "(category=%s, run=%d).",
            inserted,
            len(rows),
            category_uid,
            scrape_run_id,
        )
        return inserted
