"""PostgreSQL write-only client for the scraper container.

The scraper only needs to insert raw vacancy data and record scrape
runs.  All read, normalization and analytics operations live in the
backend package.

Classes:
- ``ScraperPostgresService`` — insert raw jobs and scrape run records.
"""

from __future__ import annotations

import logging
import json
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
    # Store ciphertext separately so both IDs are preserved.
    # job_uid prefers numeric uid (more stable); ciphertext is ~0abc...
    ciphertext: str | None = job.get("ciphertext") or None

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
        ciphertext,
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
        jobs_inserted: int = 0,
        jobs_skipped: int = 0,
        status: str = "done",
        error_message: str | None = None,
    ) -> None:
        """Mark a scrape_run as finished.

        Args:
            run_id: The scrape_run id to update.
            pages_collected: Number of pages fetched.
            jobs_collected: Total jobs seen (before dedup).
            jobs_inserted: New rows actually written to DB.
            jobs_skipped: Duplicate rows skipped (ON CONFLICT).
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
                    jobs_inserted    = %s,
                    jobs_skipped     = %s,
                    duration_seconds = EXTRACT(
                        EPOCH FROM (NOW() - started_at)
                    )::INT,
                    error_message    = %s
                WHERE id = %s
                """,
                (
                    status,
                    pages_collected,
                    jobs_collected,
                    jobs_inserted,
                    jobs_skipped,
                    error_message,
                    run_id,
                ),
            )
        self.conn.commit()
        log.info(
            "Scrape run %d finished: status=%s, "
            "pages=%d, jobs=%d (inserted=%d, skipped=%d).",
            run_id,
            status,
            pages_collected,
            jobs_collected,
            jobs_inserted,
            jobs_skipped,
        )

    # ------------------------------------------------------------------
    # Raw job insertion
    # ------------------------------------------------------------------

    def fetch_known_uids(self, category_uid: str) -> set[str]:
        """Return all job_uid values already stored for a category.

        Used to pre-filter duplicates in memory before attempting
        an INSERT, so the caller can count truly new jobs without
        waiting for ON CONFLICT to tell us after the fact.

        Args:
            category_uid: The Upwork category2_uid to query.

        Returns:
            Set of job_uid strings already in ``raw_jobs``.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT job_uid FROM raw_jobs WHERE category_uid = %s",
                (category_uid,),
            )
            return {row[0] for row in cur.fetchall()}

    def insert_raw_jobs(
        self,
        jobs: list[dict[str, Any]],
        scrape_run_id: int,
        category_uid: str,
        category_name: str,
        known_uids: set[str] | None = None,
    ) -> tuple[int, int]:
        """Bulk-insert raw job dicts into the ``raw_jobs`` table.

        Skips jobs whose ``job_uid`` already exists for this category
        (``ON CONFLICT (category_uid, job_uid) DO NOTHING``).

        If ``known_uids`` is provided (a set pre-loaded via
        ``fetch_known_uids``), duplicates are filtered in Python
        before the INSERT so the caller knows the new count
        immediately without relying on rowcount heuristics.

        Args:
            jobs: List of raw job dicts from the scraper.
            scrape_run_id: The associated scrape_run id.
            category_uid: The category2_uid these jobs belong to.
            category_name: Human-readable category name.
            known_uids: Optional set of already-stored job_uids for
                this category.  Updated in-place with newly inserted
                uids so it stays current across multiple calls.

        Returns:
            Tuple of (inserted_count, duplicate_count).
        """
        if not jobs:
            return 0, 0

        rows: list[tuple[Any, ...]] = []
        pre_dups = 0
        for job in jobs:
            row = _extract_row(
                job, scrape_run_id, category_uid, category_name
            )
            if row is None:
                continue
            # row[3] is job_uid (index matches _extract_row tuple order)
            job_uid_val: str = row[3]
            if known_uids is not None and job_uid_val in known_uids:
                pre_dups += 1
                continue
            rows.append(row)

        if not rows:
            log.info(
                "All %d jobs pre-filtered as duplicates "
                "(category=%s).",
                len(jobs), category_uid,
            )
            return 0, len(jobs)

        with self.conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO raw_jobs (
                    scrape_run_id,
                    category_uid,
                    category_name,
                    job_uid,
                    ciphertext,
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

        # Update the in-memory set with newly inserted uids
        if known_uids is not None:
            for row in rows:
                known_uids.add(row[3])

        total_dups = pre_dups + (len(rows) - inserted)
        log.info(
            "Inserted %d/%d raw jobs — %d pre-filtered + %d DB dups "
            "(category=%s, run=%d).",
            inserted,
            len(jobs),
            pre_dups,
            len(rows) - inserted,
            category_uid,
            scrape_run_id,
        )
        return inserted, total_dups

    # ------------------------------------------------------------------
    # Proxy usage snapshots
    # ------------------------------------------------------------------

    def insert_proxy_usage_snapshot(
        self,
        provider: str,
        source_endpoint: str,
        requests_used: int | None,
        bytes_used: int | None,
        bytes_remaining: int | None,
        bytes_limit: int | None,
        raw_payload: dict[str, Any],
    ) -> int:
        """Store one proxy usage snapshot row and return inserted id."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO proxy_usage_snapshots (
                    provider,
                    source_endpoint,
                    requests_used,
                    bytes_used,
                    bytes_remaining,
                    bytes_limit,
                    raw_payload,
                    captured_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
                RETURNING id
                """,
                (
                    provider,
                    source_endpoint,
                    requests_used,
                    bytes_used,
                    bytes_remaining,
                    bytes_limit,
                    json.dumps(raw_payload),
                ),
            )
            snapshot_id: int = cur.fetchone()[0]
        self.conn.commit()
        log.info(
            "Proxy usage snapshot stored id=%d provider=%s bytes_used=%s requests=%s",
            snapshot_id,
            provider,
            bytes_used,
            requests_used,
        )
        return snapshot_id

