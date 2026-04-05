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

    def get_stats(self) -> dict[str, int]:
        """Return job counts grouped by category_name.

        Returns:
            Dict mapping category name to job count,
            sorted by count descending.
        """
        sql = """
        SELECT
            COALESCE(NULLIF(category_name, ''), 'Unknown') AS category,
            COUNT(*) AS cnt
        FROM raw_jobs
        GROUP BY category
        ORDER BY cnt DESC;
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        return {row[0]: row[1] for row in rows}

    def search_jobs(
        self,
        query: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Full-text search over job titles and descriptions.

        Args:
            query: Search keywords.
            limit: Maximum number of results to return.

        Returns:
            List of matching job dicts with keys:
            uid, title, category_name.
        """
        sql = """
        SELECT uid, title, category_name
        FROM raw_jobs
        WHERE
            to_tsvector('english', title || ' ' || COALESCE(description, ''))
            @@ plainto_tsquery('english', %(query)s)
        ORDER BY published_on DESC NULLS LAST
        LIMIT %(limit)s;
        """
        with self._connect() as conn:
            with conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            ) as cur:
                cur.execute(sql, {"query": query, "limit": limit})
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def ensure_subscriptions_table(self) -> None:
        """Create subscriptions table if it does not exist."""
        ddl = """
        CREATE TABLE IF NOT EXISTS subscriptions (
            id BIGSERIAL PRIMARY KEY,
            telegram_user_id BIGINT NOT NULL UNIQUE,
            plan TEXT NOT NULL,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.commit()

    def upsert_subscription(
        self,
        telegram_user_id: int,
        plan: str,
        stripe_customer_id: str | None = None,
        stripe_subscription_id: str | None = None,
        status: str = "active",
    ) -> None:
        """Insert or update a user subscription.

        Args:
            telegram_user_id: Telegram user ID.
            plan: Plan name — 'free', 'plus', or 'pro_plus'.
            stripe_customer_id: Stripe customer ID.
            stripe_subscription_id: Stripe subscription ID.
            status: Subscription status.
        """
        self.ensure_subscriptions_table()
        sql = """
        INSERT INTO subscriptions (
            telegram_user_id, plan,
            stripe_customer_id, stripe_subscription_id, status
        ) VALUES (
            %(telegram_user_id)s, %(plan)s,
            %(stripe_customer_id)s, %(stripe_subscription_id)s,
            %(status)s
        )
        ON CONFLICT (telegram_user_id) DO UPDATE SET
            plan = EXCLUDED.plan,
            stripe_customer_id = EXCLUDED.stripe_customer_id,
            stripe_subscription_id = EXCLUDED.stripe_subscription_id,
            status = EXCLUDED.status,
            updated_at = NOW();
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {
                    "telegram_user_id": telegram_user_id,
                    "plan": plan,
                    "stripe_customer_id": stripe_customer_id,
                    "stripe_subscription_id": (
                        stripe_subscription_id
                    ),
                    "status": status,
                })
            conn.commit()
        logger.info(
            "Subscription upserted: user=%s plan=%s status=%s",
            telegram_user_id, plan, status,
        )

    def get_subscription(
        self,
        telegram_user_id: int,
    ) -> dict[str, Any] | None:
        """Fetch the subscription record for a Telegram user.

        Args:
            telegram_user_id: Telegram user ID.

        Returns:
            Subscription dict or None if not found.
        """
        self.ensure_subscriptions_table()
        sql = """
        SELECT
            telegram_user_id, plan,
            stripe_customer_id, stripe_subscription_id,
            status, created_at, updated_at
        FROM subscriptions
        WHERE telegram_user_id = %(telegram_user_id)s;
        """
        with self._connect() as conn:
            with conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            ) as cur:
                cur.execute(
                    sql,
                    {"telegram_user_id": telegram_user_id},
                )
                row = cur.fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Bot users table (Telegram profile data)
    # ------------------------------------------------------------------

    def ensure_bot_users_table(self) -> None:
        """Create bot_users table to store Telegram profile data."""
        ddl = """
        CREATE TABLE IF NOT EXISTS bot_users (
            telegram_user_id BIGINT PRIMARY KEY,
            first_name TEXT NOT NULL DEFAULT '',
            last_name TEXT NOT NULL DEFAULT '',
            username TEXT NOT NULL DEFAULT '',
            first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.commit()
        logger.info("Table bot_users is ready.")

    def upsert_bot_user(
        self,
        telegram_user_id: int,
        first_name: str,
        last_name: str,
        username: str,
    ) -> None:
        """Insert or update a Telegram user's profile data.

        Args:
            telegram_user_id: Telegram user ID.
            first_name: User's first name.
            last_name: User's last name (may be empty).
            username: User's @username (without @, may be empty).
        """
        self.ensure_bot_users_table()
        sql = """
        INSERT INTO bot_users (
            telegram_user_id, first_name, last_name,
            username, last_seen
        ) VALUES (
            %(telegram_user_id)s, %(first_name)s, %(last_name)s,
            %(username)s, NOW()
        )
        ON CONFLICT (telegram_user_id) DO UPDATE SET
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            username = EXCLUDED.username,
            last_seen = NOW();
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {
                    "telegram_user_id": telegram_user_id,
                    "first_name": first_name,
                    "last_name": last_name or "",
                    "username": username or "",
                })
            conn.commit()
        logger.debug(
            "bot_users upserted: user=%s", telegram_user_id
        )

    def get_all_users_for_sheet(
        self,
    ) -> list[dict[str, Any]]:
        """Return all bot users joined with their subscription data.

        Used for a full Google Sheets sync.  Users who have no
        subscription record are returned with plan='free' and
        status='none'.

        Returns:
            List of dicts with keys matching the Sheets columns.
        """
        self.ensure_bot_users_table()
        self.ensure_subscriptions_table()
        sql = """
        SELECT
            u.telegram_user_id,
            u.first_name,
            u.last_name,
            u.username,
            COALESCE(s.plan, 'free')  AS plan,
            COALESCE(s.status, 'none') AS status,
            COALESCE(s.stripe_customer_id, '') AS stripe_customer_id,
            COALESCE(s.stripe_subscription_id, '')
                AS stripe_subscription_id,
            u.first_seen,
            u.last_seen AS last_updated
        FROM bot_users u
        LEFT JOIN subscriptions s
            ON s.telegram_user_id = u.telegram_user_id
        ORDER BY u.first_seen;
        """
        with self._connect() as conn:
            with conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            ) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def get_user_for_sheet(
        self,
        telegram_user_id: int,
    ) -> dict[str, Any] | None:
        """Return one bot user joined with subscription data for Sheets upsert."""
        self.ensure_bot_users_table()
        self.ensure_subscriptions_table()
        sql = """
        SELECT
            u.telegram_user_id,
            u.first_name,
            u.last_name,
            u.username,
            COALESCE(s.plan, 'free')  AS plan,
            COALESCE(s.status, 'none') AS status,
            COALESCE(s.stripe_customer_id, '') AS stripe_customer_id,
            COALESCE(s.stripe_subscription_id, '')
                AS stripe_subscription_id,
            u.first_seen,
            u.last_seen AS last_updated
        FROM bot_users u
        LEFT JOIN subscriptions s
            ON s.telegram_user_id = u.telegram_user_id
        WHERE u.telegram_user_id = %(telegram_user_id)s
        LIMIT 1;
        """
        with self._connect() as conn:
            with conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            ) as cur:
                cur.execute(sql, {"telegram_user_id": telegram_user_id})
                row = cur.fetchone()
        return dict(row) if row else None

    def get_subscription_by_stripe_customer(
        self,
        stripe_customer_id: str,
    ) -> dict[str, Any] | None:
        """Fetch a subscription by Stripe customer ID.

        Args:
            stripe_customer_id: Stripe customer ID string.

        Returns:
            Subscription dict or None if not found.
        """
        self.ensure_subscriptions_table()
        sql = """
        SELECT
            telegram_user_id, plan,
            stripe_customer_id, stripe_subscription_id,
            status, created_at, updated_at
        FROM subscriptions
        WHERE stripe_customer_id = %(customer_id)s;
        """
        with self._connect() as conn:
            with conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            ) as cur:
                cur.execute(
                    sql,
                    {"customer_id": stripe_customer_id},
                )
                row = cur.fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Support feedback events (Telegram Contact Support flow)
    # ------------------------------------------------------------------

    def ensure_support_feedback_events_table(self) -> None:
        """Create support_feedback_events table for Grafana dashboard."""
        ddl = """
        CREATE TABLE IF NOT EXISTS support_feedback_events (
            id BIGSERIAL PRIMARY KEY,
            telegram_user_id BIGINT NOT NULL,
            telegram_username TEXT NOT NULL DEFAULT '',
            telegram_full_name TEXT NOT NULL DEFAULT '',
            reply_channel TEXT NOT NULL, -- telegram | email | none
            reply_email TEXT NOT NULL DEFAULT '',
            feedback_message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new', -- new | in_progress | replied | closed
            assigned_to TEXT NOT NULL DEFAULT '',
            last_reply_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        ALTER TABLE support_feedback_events
            ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'new';
        ALTER TABLE support_feedback_events
            ADD COLUMN IF NOT EXISTS assigned_to TEXT NOT NULL DEFAULT '';
        ALTER TABLE support_feedback_events
            ADD COLUMN IF NOT EXISTS last_reply_at TIMESTAMPTZ;
        CREATE INDEX IF NOT EXISTS support_feedback_events_created_at_idx
            ON support_feedback_events (created_at DESC);
        CREATE INDEX IF NOT EXISTS support_feedback_events_user_id_idx
            ON support_feedback_events (telegram_user_id);
        CREATE INDEX IF NOT EXISTS support_feedback_events_status_idx
            ON support_feedback_events (status);
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.commit()

    def ensure_support_replies_table(self) -> None:
        """Create support_replies table for operator reply history."""
        ddl = """
        CREATE TABLE IF NOT EXISTS support_replies (
            id BIGSERIAL PRIMARY KEY,
            feedback_event_id BIGINT NOT NULL REFERENCES support_feedback_events(id) ON DELETE CASCADE,
            channel TEXT NOT NULL, -- telegram | email
            sent_to TEXT NOT NULL DEFAULT '',
            reply_text TEXT NOT NULL,
            operator_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL, -- sent | failed
            error_message TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS support_replies_event_id_idx
            ON support_replies (feedback_event_id);
        CREATE INDEX IF NOT EXISTS support_replies_created_at_idx
            ON support_replies (created_at DESC);
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.commit()

    def insert_support_feedback_event(
        self,
        *,
        telegram_user_id: int,
        telegram_username: str,
        telegram_full_name: str,
        reply_channel: str,
        feedback_message: str,
        reply_email: str = "",
    ) -> None:
        """Insert one support feedback event for Grafana consumption."""
        self.ensure_support_feedback_events_table()
        sql = """
        INSERT INTO support_feedback_events (
            telegram_user_id,
            telegram_username,
            telegram_full_name,
            reply_channel,
            reply_email,
            feedback_message,
            status
        ) VALUES (
            %(telegram_user_id)s,
            %(telegram_username)s,
            %(telegram_full_name)s,
            %(reply_channel)s,
            %(reply_email)s,
            %(feedback_message)s,
            'new'
        );
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {
                    "telegram_user_id": telegram_user_id,
                    "telegram_username": telegram_username or "",
                    "telegram_full_name": telegram_full_name or "",
                    "reply_channel": reply_channel,
                    "reply_email": reply_email or "",
                    "feedback_message": feedback_message,
                })
            conn.commit()

    def get_support_feedback_inbox(
        self,
        *,
        status: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Return support feedback rows for inbox views."""
        self.ensure_support_feedback_events_table()
        query = """
        SELECT
            id,
            created_at,
            telegram_user_id,
            telegram_username,
            telegram_full_name,
            reply_channel,
            NULLIF(reply_email, '') AS reply_email,
            feedback_message,
            status,
            assigned_to,
            last_reply_at
        FROM support_feedback_events
        """
        params: dict[str, Any] = {"limit": max(1, min(limit, 1000))}
        if status:
            query += " WHERE status = %(status)s"
            params["status"] = status
        query += " ORDER BY created_at DESC LIMIT %(limit)s"
        with self._connect() as conn:
            with conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            ) as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def get_support_feedback_event(
        self,
        *,
        event_id: int,
    ) -> dict[str, Any] | None:
        """Return one support feedback event by ID."""
        self.ensure_support_feedback_events_table()
        sql = """
        SELECT
            id,
            created_at,
            telegram_user_id,
            telegram_username,
            telegram_full_name,
            reply_channel,
            reply_email,
            feedback_message,
            status,
            assigned_to,
            last_reply_at
        FROM support_feedback_events
        WHERE id = %(event_id)s
        LIMIT 1;
        """
        with self._connect() as conn:
            with conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            ) as cur:
                cur.execute(sql, {"event_id": event_id})
                row = cur.fetchone()
        return dict(row) if row else None

    def upsert_support_feedback_status(
        self,
        *,
        event_id: int,
        status: str,
        assigned_to: str = "",
    ) -> bool:
        """Update support feedback status and assignment."""
        self.ensure_support_feedback_events_table()
        sql = """
        UPDATE support_feedback_events
        SET
            status = %(status)s,
            assigned_to = %(assigned_to)s
        WHERE id = %(event_id)s;
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {
                    "event_id": event_id,
                    "status": status,
                    "assigned_to": assigned_to,
                })
                updated = cur.rowcount > 0
            conn.commit()
        return updated

    def mark_support_feedback_replied(
        self,
        *,
        event_id: int,
        assigned_to: str = "",
    ) -> bool:
        """Mark feedback event as replied and set reply timestamp."""
        self.ensure_support_feedback_events_table()
        sql = """
        UPDATE support_feedback_events
        SET
            status = 'replied',
            assigned_to = %(assigned_to)s,
            last_reply_at = NOW()
        WHERE id = %(event_id)s;
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {
                    "event_id": event_id,
                    "assigned_to": assigned_to,
                })
                updated = cur.rowcount > 0
            conn.commit()
        return updated

    def insert_support_reply(
        self,
        *,
        feedback_event_id: int,
        channel: str,
        sent_to: str,
        reply_text: str,
        operator_name: str,
        status: str,
        error_message: str = "",
    ) -> None:
        """Store one support reply delivery attempt."""
        self.ensure_support_feedback_events_table()
        self.ensure_support_replies_table()
        sql = """
        INSERT INTO support_replies (
            feedback_event_id,
            channel,
            sent_to,
            reply_text,
            operator_name,
            status,
            error_message
        ) VALUES (
            %(feedback_event_id)s,
            %(channel)s,
            %(sent_to)s,
            %(reply_text)s,
            %(operator_name)s,
            %(status)s,
            %(error_message)s
        );
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {
                    "feedback_event_id": feedback_event_id,
                    "channel": channel,
                    "sent_to": sent_to,
                    "reply_text": reply_text,
                    "operator_name": operator_name,
                    "status": status,
                    "error_message": error_message,
                })
            conn.commit()

    # ------------------------------------------------------------------
    # Bot chat usage tracking (for trial/plan limits)
    # ------------------------------------------------------------------

    def ensure_bot_chat_usage_table(self) -> None:
        """Create bot_chat_usage table for per-user request tracking."""
        ddl = """
        CREATE TABLE IF NOT EXISTS bot_chat_usage (
            id BIGSERIAL PRIMARY KEY,
            telegram_user_id BIGINT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS bot_chat_usage_user_time_idx
        ON bot_chat_usage (telegram_user_id, created_at DESC);
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.commit()

    def count_bot_chat_requests_last_24h(
        self,
        telegram_user_id: int,
    ) -> int:
        """Return how many chat requests a user made in the last 24h."""
        self.ensure_bot_chat_usage_table()
        sql = """
        SELECT COUNT(*)
        FROM bot_chat_usage
        WHERE telegram_user_id = %(telegram_user_id)s
          AND created_at >= NOW() - INTERVAL '24 hours';
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"telegram_user_id": telegram_user_id})
                row = cur.fetchone()
        return int(row[0]) if row else 0

    def insert_bot_chat_request(
        self,
        telegram_user_id: int,
        plan: str = "free",
    ) -> None:
        """Log a single bot chat request event."""
        self.ensure_bot_chat_usage_table()
        sql = """
        INSERT INTO bot_chat_usage (telegram_user_id, plan)
        VALUES (%(telegram_user_id)s, %(plan)s);
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {
                    "telegram_user_id": telegram_user_id,
                    "plan": plan,
                })
            conn.commit()

