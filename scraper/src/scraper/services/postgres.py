"""PostgreSQL write-only client for the scraper container.

The scraper only needs to insert raw vacancy data and record scrape
runs.  All read, normalization and analytics operations live in the
backend package.

Classes:
- ``ScraperPostgresService`` — insert raw jobs and scrape run records.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import psycopg2
from psycopg2.extras import execute_values

log = logging.getLogger(__name__)


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
            "Scrape run %d started for category %s.",
            run_id, category_name,
        )
        return run_id

    def finish_scrape_run(
        self,
        run_id: int,
        jobs_inserted: int,
        status: str = "done",
    ) -> None:
        """Mark a scrape_run as finished.

        Args:
            run_id: The scrape_run id to update.
            jobs_inserted: Number of job rows inserted.
            status: Final status string (``"done"`` or ``"error"``).
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE scrape_runs
                SET status = %s,
                    finished_at = NOW(),
                    jobs_inserted = %s
                WHERE id = %s
                """,
                (status, jobs_inserted, run_id),
            )
        self.conn.commit()
        log.info(
            "Scrape run %d finished: status=%s, jobs=%d.",
            run_id, status, jobs_inserted,
        )

    # ------------------------------------------------------------------
    # Raw job insertion
    # ------------------------------------------------------------------

    def insert_raw_jobs(
        self,
        jobs: list[dict[str, Any]],
        scrape_run_id: int,
        category_uid: str,
    ) -> int:
        """Bulk-insert raw job dicts into the raw_jobs table.

        Skips jobs whose ``uid`` already exists (ON CONFLICT DO NOTHING).

        Args:
            jobs: List of raw job dicts from the scraper.
            scrape_run_id: The associated scrape_run id.
            category_uid: The category2_uid these jobs belong to.

        Returns:
            Number of rows actually inserted (duplicates excluded).
        """
        if not jobs:
            return 0

        rows = [
            (
                job.get("uid") or job.get("id"),
                category_uid,
                scrape_run_id,
                json.dumps(job, ensure_ascii=False),
            )
            for job in jobs
            if job.get("uid") or job.get("id")
        ]

        with self.conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO raw_jobs
                    (uid, category_uid, scrape_run_id, raw_json)
                VALUES %s
                ON CONFLICT (uid) DO NOTHING
                """,
                rows,
            )
            inserted: int = cur.rowcount
        self.conn.commit()
        log.info(
            "Inserted %d/%d raw jobs (category=%s, run=%d).",
            inserted, len(rows), category_uid, scrape_run_id,
        )
        return inserted
