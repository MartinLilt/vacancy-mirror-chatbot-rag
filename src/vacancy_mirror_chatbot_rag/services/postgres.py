"""PostgreSQL service for job pipeline."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


class PostgresJobExportService:
    """PostgreSQL service for job pipeline."""

    def __init__(self, db_url: str | None = None) -> None:
        self._db_url = db_url or os.environ["DB_URL"]

    def ensure_table(self) -> None:
        """Create raw_jobs table."""
        ddl = """
        CREATE TABLE IF NOT EXISTS raw_jobs (
            uid TEXT PRIMARY KEY,
            ciphertext TEXT,
            title TEXT NOT NULL,
            description TEXT,
            skills TEXT,
            category_uid TEXT,
            category_name TEXT,
            created_on TEXT,
            published_on TEXT,
            raw_json JSONB NOT NULL,
            imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.commit()
        logger.info("Table raw_jobs is ready.")

    def insert_jobs(
        self,
        items: list[dict[str, Any]],
        *,
        category_uid: str = "",
        category_name: str = "",
    ) -> int:
        """Insert jobs into raw_jobs."""
        if not items:
            return 0

        rows = [
            self._build_row(item, category_uid, category_name)
            for item in items
            if isinstance(item, dict)
        ]

        sql = """
        INSERT INTO raw_jobs (
            uid, ciphertext, title, description,
            skills, category_uid, category_name,
            created_on, published_on, raw_json
        ) VALUES (
            %(uid)s, %(ciphertext)s, %(title)s,
            %(description)s, %(skills)s, %(category_uid)s,
            %(category_name)s, %(created_on)s,
            %(published_on)s, %(raw_json)s
        )
        ON CONFLICT (uid) DO NOTHING;
        """

        with self._connect() as conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_batch(
                    cur, sql, rows, page_size=200
                )
                inserted = cur.rowcount
            conn.commit()

        logger.info("Inserted %d new jobs.", inserted)
        return inserted

    def ensure_pattern_jobs_table(self) -> None:
        """Create pattern_jobs table."""
        ddl = """
        CREATE TABLE IF NOT EXISTS pattern_jobs (
            jobid TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            "desc" TEXT,
            skills TEXT,
            source_uid TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.commit()
        logger.info("Table pattern_jobs is ready.")

    def build_pattern_jobs_from_raw(self) -> int:
        """Build pattern_jobs from raw_jobs."""
        self.ensure_pattern_jobs_table()

        sql = """
        INSERT INTO pattern_jobs (
            jobid, title, "desc", skills, source_uid
        )
        SELECT DISTINCT
            uid, title, description, skills, uid
        FROM raw_jobs
        WHERE uid NOT IN (
            SELECT source_uid FROM pattern_jobs
        )
        ON CONFLICT (jobid) DO NOTHING;
        """

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                inserted = cur.rowcount
            conn.commit()

        logger.info("Built pattern_jobs: %d new rows.", inserted)
        return inserted

    def get_pattern_jobs(self) -> list[dict[str, Any]]:
        """Fetch all pattern jobs."""
        sql = """
        SELECT jobid, title, "desc", skills
        FROM pattern_jobs
        ORDER BY created_at
        """
        with self._connect() as conn:
            with conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            ) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def ensure_pattern_normalized_jobs_table(self) -> None:
        """Create pattern_normalized_jobs table."""
        ddl = """
        CREATE TABLE IF NOT EXISTS pattern_normalized_jobs (
            jobid TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            "desc" TEXT,
            skills TEXT,
            source_jobid TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.commit()
        logger.info("Table pattern_normalized_jobs is ready.")

    def build_normalized_jobs_from_pattern(
        self,
        normalized_rows: list[dict[str, str]],
    ) -> int:
        """Insert normalized jobs."""
        self.ensure_pattern_normalized_jobs_table()

        sql = """
        INSERT INTO pattern_normalized_jobs (
            jobid, title, "desc", skills, source_jobid
        ) VALUES (
            %(jobid)s, %(title)s, %(desc)s,
            %(skills)s, %(source_jobid)s
        )
        ON CONFLICT (jobid) DO NOTHING;
        """

        with self._connect() as conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_batch(
                    cur, sql, normalized_rows, page_size=200
                )
                inserted = cur.rowcount
            conn.commit()

        logger.info("Built normalized jobs: %d new rows.", inserted)
        return inserted

    def get_normalized_jobs(self) -> list[dict[str, Any]]:
        """Fetch all normalized jobs."""
        sql = """
        SELECT jobid, title, "desc", skills
        FROM pattern_normalized_jobs
        ORDER BY created_at
        """
        with self._connect() as conn:
            with conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            ) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def ensure_job_embeddings_table(self) -> None:
        """Create job_embeddings table."""
        ddl = """
        CREATE TABLE IF NOT EXISTS job_embeddings (
            jobid TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            embedding vector(1024),
            source_jobid TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS job_embeddings_vector_idx
        ON job_embeddings USING ivfflat
        (embedding vector_cosine_ops) WITH (lists = 10);
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.commit()
        logger.info("Table job_embeddings is ready.")

    def insert_job_embeddings(
        self,
        embeddings_data: list[dict[str, Any]],
    ) -> int:
        """Insert job embeddings."""
        self.ensure_job_embeddings_table()

        sql = """
        INSERT INTO job_embeddings (
            jobid, text, embedding, source_jobid
        ) VALUES (
            %(jobid)s, %(text)s, %(embedding)s,
            %(source_jobid)s
        )
        ON CONFLICT (jobid) DO NOTHING;
        """

        with self._connect() as conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_batch(
                    cur, sql, embeddings_data, page_size=200
                )
                inserted = cur.rowcount
            conn.commit()

        logger.info("Inserted embeddings: %d new rows.", inserted)
        return inserted

    def get_job_embeddings(self) -> list[dict[str, Any]]:
        """Fetch all job embeddings."""
        sql = """
        SELECT jobid, text, embedding, source_jobid
        FROM job_embeddings
        ORDER BY created_at
        """
        with self._connect() as conn:
            with conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            ) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def ensure_job_clusters_table(self) -> None:
        """Create job_clusters table."""
        ddl = """
        CREATE TABLE IF NOT EXISTS job_clusters (
            cluster_id SERIAL PRIMARY KEY,
            jobids TEXT[] NOT NULL,
            size INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.commit()
        logger.info("Table job_clusters is ready.")

    def insert_job_clusters(
        self,
        clusters_data: list[dict[str, Any]],
    ) -> int:
        """Insert job clusters."""
        self.ensure_job_clusters_table()

        sql = """
        INSERT INTO job_clusters (jobids, size)
        VALUES (%(jobids)s, %(size)s);
        """

        with self._connect() as conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_batch(
                    cur, sql, clusters_data, page_size=200
                )
                inserted = cur.rowcount
            conn.commit()

        logger.info("Inserted clusters: %d new rows.", inserted)
        return inserted

    def get_job_clusters(self) -> list[dict[str, Any]]:
        """Fetch all job clusters."""
        sql = """
        SELECT cluster_id, jobids, size
        FROM job_clusters
        ORDER BY created_at
        """
        with self._connect() as conn:
            with conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            ) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def ensure_profiles_table(self) -> None:
        """Create profiles table."""
        ddl = """
        CREATE TABLE IF NOT EXISTS profiles (
            id SERIAL PRIMARY KEY,
            cluster_id INTEGER,
            role_name TEXT,
            demand_type TEXT,
            demand_ratio FLOAT,
            total_matching INTEGER,
            semantic_core TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.commit()
        logger.info("Table profiles is ready.")

    def insert_profiles(
        self,
        profiles_data: list[dict[str, Any]],
    ) -> int:
        """Insert profiles."""
        self.ensure_profiles_table()

        sql = """
        INSERT INTO profiles (
            cluster_id, role_name, demand_type,
            demand_ratio, total_matching, category_uid, category_name
        ) VALUES (
            %(cluster_id)s, %(role_name)s,
            %(demand_type)s, %(demand_ratio)s,
            %(total_matching)s, %(category_uid)s, %(category_name)s
        );
        """

        with self._connect() as conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_batch(
                    cur, sql, profiles_data, page_size=200
                )
                inserted = cur.rowcount
            conn.commit()

        logger.info("Inserted profiles: %d records.", inserted)
        return inserted

    def get_profiles(self) -> list[dict[str, Any]]:
        """Fetch all profiles."""
        sql = """
        SELECT id, cluster_id, role_name, demand_type,
               demand_ratio, total_matching
        FROM profiles
        ORDER BY created_at
        """
        with self._connect() as conn:
            with conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            ) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def _build_row(
        self,
        item: dict[str, Any],
        category_uid: str,
        category_name: str,
    ) -> dict[str, Any]:
        """Convert job dict to DB row."""
        uid = str(item.get("uid") or item.get("id") or "").strip()
        if not uid:
            uid = str(item.get("ciphertext") or "").strip()

        skills = self._extract_skills(item)

        return {
            "uid": uid,
            "ciphertext": str(
                item.get("ciphertext") or ""
            ).strip(),
            "title": str(item.get("title") or "").strip(),
            "description": str(
                item.get("description") or ""
            ).strip(),
            "skills": skills,
            "category_uid": category_uid,
            "category_name": category_name,
            "created_on": str(
                item.get("createdOn") or ""
            ).strip(),
            "published_on": str(
                item.get("publishedOn") or ""
            ).strip(),
            "raw_json": json.dumps(item, ensure_ascii=False),
        }

    @staticmethod
    def _extract_skills(item: dict[str, Any]) -> str:
        """Extract skills from attrs list."""
        attrs = item.get("attrs")
        if not isinstance(attrs, list):
            return ""
        labels = [
            str(a.get("prefLabel", "")).strip()
            for a in attrs
            if isinstance(a, dict) and a.get("prefLabel")
        ]
        return " | ".join(labels)

    def _connect(self) -> psycopg2.extensions.connection:
        return psycopg2.connect(self._db_url)
