"""Scraper API — FastAPI microservice running inside the scraper container.

Endpoints
---------
GET  /health                   — liveness check
GET  /status                   — current scraper status (running / idle)
GET  /categories               — list of all categories from DB
POST /scrape                   — trigger a scrape run
GET  /jobs                     — paginated raw jobs from DB
POST /jobs/clear               — truncate raw_jobs (weekly reset)

Auth
----
All mutating endpoints require the X-API-Key header matching API_KEY env var.
GET endpoints (/health, /status, /categories, /jobs) are public.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from typing import Any

import psycopg2
import psycopg2.extras
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from scraper.categories import CATEGORY_UIDS

log = logging.getLogger("scraper_api")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATABASE_URL: str = os.environ["DATABASE_URL"]
API_KEY: str = os.environ.get("SCRAPER_API_KEY", "changeme")

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Scraper API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Scraper state (in-memory, single-process)
# ---------------------------------------------------------------------------

_scraper_lock = threading.Lock()
_scraper_state: dict[str, Any] = {
    "status": "idle",           # idle | running
    "pid": None,
    "started_at": None,
    "category_uid": None,
    "category_name": None,
    "max_pages": None,
}


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def require_api_key(x_api_key: str = Header(...)) -> None:
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ---------------------------------------------------------------------------
# DB helper
# ---------------------------------------------------------------------------

def get_conn() -> psycopg2.extensions.connection:
    return psycopg2.connect(DATABASE_URL)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ScrapeRequest(BaseModel):
    category_uid: str
    max_pages: int = 10
    delay_min: int = 30
    delay_max: int = 45
    stop_at_hour: int = 23


class ScrapeResponse(BaseModel):
    ok: bool
    message: str


class ClearResponse(BaseModel):
    ok: bool
    deleted_rows: int


# ---------------------------------------------------------------------------
# Background scraper runner
# ---------------------------------------------------------------------------

def _run_scraper(req: ScrapeRequest) -> None:
    """Launch scraper in subprocess and track state."""
    cmd = [
        "python", "-m", "scraper.cli", "scrape",
        "--uid", req.category_uid,
        "--max-pages", str(req.max_pages),
        "--delay-min", str(req.delay_min),
        "--delay-max", str(req.delay_max),
        "--stop-at-hour", str(req.stop_at_hour),
    ]

    log.info("Starting scraper: %s", " ".join(cmd))

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        with _scraper_lock:
            _scraper_state["pid"] = proc.pid

        # Stream logs without buffering
        for line in proc.stdout:
            log.info("[scraper] %s", line.rstrip())

        proc.wait()
        log.info("Scraper process finished (rc=%d)", proc.returncode)

    except Exception as exc:
        log.error("Scraper subprocess error: %s", exc)
    finally:
        with _scraper_lock:
            _scraper_state["status"] = "idle"
            _scraper_state["pid"] = None
            _scraper_state["started_at"] = None
            _scraper_state["category_uid"] = None
            _scraper_state["category_name"] = None
            _scraper_state["max_pages"] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/status")
def status() -> dict:
    with _scraper_lock:
        return dict(_scraper_state)


@app.get("/categories")
def list_categories() -> list[dict]:
    """Return categories from DB (distinct category_uid/name from scrape_runs).
    Falls back to static CATEGORY_UIDS if DB has no data yet.
    """
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT DISTINCT category_uid, category_name
                FROM scrape_runs
                ORDER BY category_name
                """
            )
            rows = cur.fetchall()
        conn.close()

        if rows:
            return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("DB categories query failed: %s — using static list", exc)

    # Fallback: static registry
    return [
        {"category_uid": uid, "category_name": name}
        for name, uid in sorted(CATEGORY_UIDS.items())
    ]


@app.post("/scrape", dependencies=[Depends(require_api_key)])
def trigger_scrape(req: ScrapeRequest) -> ScrapeResponse:
    """Trigger a scrape run. Returns 409 if already running."""
    with _scraper_lock:
        if _scraper_state["status"] == "running":
            raise HTTPException(
                status_code=409,
                detail="Scraper already running. Wait for it to finish.",
            )

        if req.category_uid not in CATEGORY_UIDS.values():
            raise HTTPException(
                status_code=400,
                detail=f"Unknown category_uid: {req.category_uid}",
            )

        uid_to_name = {v: k for k, v in CATEGORY_UIDS.items()}
        from datetime import datetime, timezone

        _scraper_state["status"] = "running"
        _scraper_state["category_uid"] = req.category_uid
        _scraper_state["category_name"] = uid_to_name.get(req.category_uid)
        _scraper_state["max_pages"] = req.max_pages
        _scraper_state["started_at"] = datetime.now(timezone.utc).isoformat()

    thread = threading.Thread(target=_run_scraper, args=(req,), daemon=True)
    thread.start()

    return ScrapeResponse(ok=True, message="Scrape started in background.")


@app.get("/jobs")
def get_jobs(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(100, ge=1, le=1000, description="Items per page"),
    category_uid: str | None = Query(
        None, description="Filter by category UID"),
    since: str | None = Query(
        None,
        description="ISO date string, e.g. 2026-03-25. Return jobs scraped on or after this date.",
    ),
) -> dict:
    """Return paginated raw jobs from the scraper DB.

    The backend calls this endpoint to pull weekly job data.
    Pagination: use page + page_size. Returns total count for iteration.
    """
    offset = (page - 1) * page_size

    filters: list[str] = []
    params: list[Any] = []

    if category_uid:
        filters.append("category_uid = %s")
        params.append(category_uid)

    if since:
        filters.append("scraped_at >= %s::timestamptz")
        params.append(since)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Total count
            cur.execute(
                f"SELECT COUNT(*) FROM raw_jobs {where}",
                params,
            )
            total: int = cur.fetchone()["count"]

            # Page of data
            cur.execute(
                f"""
                SELECT
                    id, job_uid, category_uid, category_name,
                    title, description, published_at, job_type,
                    duration_label, client_country,
                    client_payment_verified, client_total_spent,
                    client_total_reviews, client_total_feedback,
                    enterprise_job, skills,
                    hourly_budget_min, hourly_budget_max,
                    weekly_budget, scraped_at
                FROM raw_jobs
                {where}
                ORDER BY scraped_at DESC, id DESC
                LIMIT %s OFFSET %s
                """,
                params + [page_size, offset],
            )
            rows = [dict(r) for r in cur.fetchall()]
        conn.close()
    except Exception as exc:
        log.error("DB jobs query failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "jobs": rows,
    }


@app.post("/jobs/clear", dependencies=[Depends(require_api_key)])
def clear_jobs() -> ClearResponse:
    """Truncate the raw_jobs table (called every Monday before new scrape)."""
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM raw_jobs")
            count: int = cur.fetchone()[0]
            cur.execute("TRUNCATE TABLE raw_jobs RESTART IDENTITY")
        conn.commit()
        conn.close()
        log.info("raw_jobs truncated: %d rows deleted.", count)
        return ClearResponse(ok=True, deleted_rows=count)
    except Exception as exc:
        log.error("Truncate failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
