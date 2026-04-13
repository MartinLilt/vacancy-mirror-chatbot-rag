"""Scraper API — FastAPI microservice running inside the scraper container.

Endpoints
---------
GET  /health                   — liveness check
GET  /status                   — current scraper status (running / idle)
GET  /categories               — list of all categories from DB
POST /scrape                   — trigger a scrape run
GET  /jobs                     — paginated raw jobs from DB
POST /jobs/clear               — truncate raw_jobs (weekly reset)
GET  /chaos-state              — per-category chaos scraper progress

Auth
----
All mutating endpoints require the X-API-Key header matching API_KEY env var.
GET endpoints (/health, /status, /categories, /jobs, /chaos-state) are public.
"""

from __future__ import annotations

import collections
import json
import logging
import os
import signal
import subprocess
import threading
from pathlib import Path
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
API_KEY: str = os.environ.get("SCRAPER_API_KEY") or os.environ.get("API_KEY", "")

# Security: fail fast if API key is not set or is default value
if not API_KEY or API_KEY == "changeme":
    log.warning(
        "⚠️  SCRAPER_API_KEY not set or using default value! "
        "API will be vulnerable. Set a strong random key in production."
    )
    if os.environ.get("PRODUCTION", "false").lower() == "true":
        raise RuntimeError(
            "SCRAPER_API_KEY must be set in production environment"
        )

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

# Ring buffer — last 200 log lines from scraper subprocess
_log_buffer: collections.deque = collections.deque(maxlen=200)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def require_api_key(x_api_key: str = Header(...)) -> None:
    if x_api_key != API_KEY:
        # Log unauthorized attempts for security monitoring
        log.warning(
            "Unauthorized API access attempt - invalid key: %s...",
            x_api_key[:8] if len(x_api_key) >= 8 else "***"
        )
        raise HTTPException(status_code=401, detail="Invalid API key")


def optional_api_key(x_api_key: str | None = Header(None)) -> bool:
    """Optional API key check for read-only endpoints.
    
    Returns True if valid key provided, False if no key.
    Raises 401 if invalid key provided.
    
    Use this for GET endpoints that should be public for monitoring
    but can optionally require auth via X-API-Key header.
    """
    if x_api_key is None:
        return False
    if x_api_key != API_KEY:
        log.warning(
            "Unauthorized API access attempt - invalid key: %s...",
            x_api_key[:8] if len(x_api_key) >= 8 else "***"
        )
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


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

def _push_log(msg: str) -> None:
    """Append a line to the log buffer and logger."""
    _log_buffer.append(msg)
    log.info("[scraper] %s", msg)


def _run_scraper(req: ScrapeRequest) -> None:
    """Launch scraper in subprocess and track state."""
    from datetime import datetime, timezone

    cmd = [
        "python", "-m", "scraper.cli", "scrape",
        "--uid", req.category_uid,
        "--max-pages", str(req.max_pages),
        "--delay-min", str(req.delay_min),
        "--delay-max", str(req.delay_max),
        "--stop-at-hour", str(req.stop_at_hour),
    ]

    uid_to_name = {v: k for k, v in CATEGORY_UIDS.items()}
    cat_name = uid_to_name.get(req.category_uid, req.category_uid)

    _push_log(f"{'='*60}")
    _push_log(
        f"▶ SCRAPE STARTED  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    _push_log(f"  Category : {cat_name}")
    _push_log(f"  Max pages: {req.max_pages}  (~{req.max_pages * 50} jobs)")
    _push_log(f"  Delay    : {req.delay_min}–{req.delay_max}s between pages")
    _push_log(f"{'='*60}")

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

        _push_log(f"  PID {proc.pid} — subprocess launched")

        # Stream logs into ring buffer + logger
        for line in proc.stdout:
            stripped = line.rstrip()
            if stripped:
                _push_log(stripped)

        proc.wait()
        rc = proc.returncode
        _push_log(f"{'='*60}")
        if rc == 0:
            _push_log(
                f"✅ SCRAPE FINISHED  rc={rc}  {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
        else:
            _push_log(
                f"❌ SCRAPE FAILED    rc={rc}  {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
        _push_log(f"{'='*60}")
        log.info("Scraper process finished (rc=%d)", rc)

    except Exception as exc:
        _push_log(f"❌ SUBPROCESS ERROR: {exc}")
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
        state = dict(_scraper_state)

    # If the API already knows it's running, trust that.
    if state["status"] == "running":
        return state

    # Also detect scraper processes started by cron (outside the API).
    # cron runs chaos_runner.sh → python -m scraper.cli scrape-chaos
    # The FastAPI in-memory state is NOT updated in that case, so we fall
    # back to a pgrep check on the process table.
    try:
        result = subprocess.run(
            ["pgrep", "-f", "scraper.cli scrape-chaos"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            pids = [p for p in result.stdout.strip().split("\n") if p]
            pid = int(pids[0]) if pids else None
            # Approximate start time from /proc/<pid>/stat field 22 (clock ticks since boot)
            started_at = None
            if pid:
                try:
                    import time as _time
                    hz = os.sysconf("SC_CLK_TCK")
                    proc_stat = open(f"/proc/{pid}/stat").read().split()
                    uptime_secs = float(open("/proc/uptime").read().split()[0])
                    start_ticks = float(proc_stat[21])
                    age_secs = uptime_secs - start_ticks / hz
                    from datetime import datetime, timezone, timedelta
                    started_at = (
                        datetime.now(timezone.utc) - timedelta(seconds=age_secs)
                    ).isoformat()
                except Exception:
                    pass
            return {
                "status": "running",
                "pid": pid,
                "started_at": started_at,
                "category_uid": "chaos",
                "category_name": "chaos-all-categories (cron)",
                "max_pages": None,
            }
    except Exception:
        pass

    return state


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

    _log_buffer.clear()
    thread = threading.Thread(target=_run_scraper, args=(req,), daemon=True)
    thread.start()

    return ScrapeResponse(ok=True, message="Scrape started in background.")


@app.post("/stop", dependencies=[Depends(require_api_key)])
def stop_scraper() -> dict:
    """Send SIGTERM to the running scraper process."""
    with _scraper_lock:
        if _scraper_state["status"] != "running":
            raise HTTPException(
                status_code=409, detail="Scraper is not running.")
        pid = _scraper_state["pid"]

    if pid is None:
        raise HTTPException(status_code=409, detail="No PID available.")

    try:
        os.kill(pid, signal.SIGTERM)
        log.info("Sent SIGTERM to scraper pid=%d", pid)
        return {"ok": True, "message": f"SIGTERM sent to pid {pid}."}
    except ProcessLookupError:
        return {"ok": False, "message": "Process already finished."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/logs")
def get_logs(lines: int = Query(100, ge=1, le=200)) -> dict:
    """Return last N lines from the scraper log.

    Primary source: in-memory buffer (API-triggered sessions).
    Fallback: /var/log/scraper.log (cron-triggered sessions).
    """
    with _scraper_lock:
        current_status = _scraper_state["status"]
    log_lines = list(_log_buffer)[-lines:]
    # Cron-started sessions don't write to _log_buffer – tail the file instead
    if not log_lines:
        try:
            result = subprocess.run(
                ["tail", "-n", str(lines), "/var/log/scraper.log"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                log_lines = result.stdout.splitlines()
        except Exception:
            pass
    return {
        "status": current_status,
        "lines": log_lines,
        "text": "\n".join(log_lines),
    }


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


@app.post("/scrape-chaos", dependencies=[Depends(require_api_key)])
def trigger_scrape_chaos() -> ScrapeResponse:
    """Trigger one chaos scraper session manually (same as cron fires).

    Runs: python -m scraper.cli scrape-chaos --max-runtime-minutes 50
    Returns 409 if already running.
    """
    with _scraper_lock:
        if _scraper_state["status"] == "running":
            raise HTTPException(
                status_code=409,
                detail="Scraper already running. Wait for it to finish.",
            )
        from datetime import datetime, timezone
        _scraper_state["status"] = "running"
        _scraper_state["started_at"] = datetime.now(timezone.utc).isoformat()
        _scraper_state["category_uid"] = "chaos"
        _scraper_state["category_name"] = "chaos-all-categories"
        _scraper_state["max_pages"] = None
        _scraper_state["pid"] = None

    _log_buffer.clear()
    thread = threading.Thread(
        target=_run_scraper_chaos, daemon=True)
    thread.start()

    return ScrapeResponse(ok=True, message="Chaos scraper session started.")


def _run_scraper_chaos() -> None:
    """Launch scrape-chaos CLI in subprocess and stream logs."""
    from datetime import datetime, timezone

    cmd = [
        "python", "-m", "scraper.cli", "scrape-chaos",
        "--max-runtime-minutes", "50",
        "--stop-at-hour", "24",
        "--target-per-cat", str(CHAOS_TARGET_PER_CAT),
    ]

    _push_log(f"{'='*60}")
    _push_log(
        f"▶ CHAOS SESSION  "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    _push_log(
        f"  Mode: all categories, "
        f"target {CHAOS_TARGET_PER_CAT} jobs each"
    )
    _push_log(f"{'='*60}")

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
        _push_log(f"  PID {proc.pid} — subprocess launched")

        for line in proc.stdout:
            stripped = line.rstrip()
            if stripped:
                _push_log(stripped)

        proc.wait()
        rc = proc.returncode
        _push_log(f"{'='*60}")
        if rc == 0:
            _push_log(
                f"✅ CHAOS FINISHED  rc={rc}  "
                f"{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
        else:
            _push_log(
                f"❌ CHAOS FAILED    rc={rc}  "
                f"{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
        _push_log(f"{'='*60}")
    except Exception as exc:
        _push_log(f"❌ SUBPROCESS ERROR: {exc}")
        log.error("Chaos subprocess error: %s", exc)
    finally:
        with _scraper_lock:
            _scraper_state["status"] = "idle"
            _scraper_state["pid"] = None
            _scraper_state["started_at"] = None
            _scraper_state["category_uid"] = None
            _scraper_state["category_name"] = None
            _scraper_state["max_pages"] = None


# ---------------------------------------------------------------------------
# Chaos-state endpoint
# ---------------------------------------------------------------------------

# uid → human name lookup (inverse of CATEGORY_UIDS)
_UID_TO_NAME: dict[str, str] = {v: k for k, v in CATEGORY_UIDS.items()}

CHAOS_STATE_PATH = Path(os.environ.get(
    "CHAOS_STATE_FILE", "/app/data/chaos_state.json"))
CHAOS_TARGET_PER_CAT = int(os.environ.get("CHAOS_TARGET_PER_CAT", "5000"))


@app.get("/chaos-state")
def chaos_state() -> dict:
    """Return per-category chaos scraper progress read from the state file.

    Response shape:
    {
      "target_per_cat": 1000,
      "state_file": "/app/data/chaos_state.json",
      "categories": [
        {
          "uid": "...",
          "name": "Web, Mobile & Software Dev",
          "collected": 62,
          "visited_pages": 5,
          "pct": 62.0
        },
        ...
      ],
      "total_collected": 744
    }
    """
    if not CHAOS_STATE_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=f"State file not found: {CHAOS_STATE_PATH}",
        )

    try:
        raw = json.loads(CHAOS_STATE_PATH.read_text())
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Cannot read state file: {exc}")

    _TIER_LABELS = {1: "Entry", 2: "Intermediate", 3: "Expert"}

    categories = []
    total_collected = 0
    for uid, data in raw.items():
        collected = data.get("collected", 0)
        total_upwork_jobs = data.get("total_upwork_jobs", 0)

        # ── Support both old format (top-level visited_pages / real_max_page)
        # and new per-tier format (tiers.{"1","2","3"}.visited_pages etc.) ──
        tiers_raw: dict = data.get("tiers", {})
        if tiers_raw:
            # New format: aggregate across all 3 tiers
            visited_pages = sum(
                len(t.get("visited_pages", []))
                for t in tiers_raw.values()
            )
            visited_pages_list: list[int] = sorted(
                p
                for t in tiers_raw.values()
                for p in t.get("visited_pages", [])
            )
            real_max_page = sum(
                t.get("real_max_page", 0) for t in tiers_raw.values()
            )
            max_collectable = sum(
                min(t.get("real_max_page", 0), 100) * 50
                for t in tiers_raw.values()
            )
            # Per-tier breakdown for dashboard
            tiers_info = []
            for tier_key in ("1", "2", "3"):
                tier_num = int(tier_key)
                t = tiers_raw.get(tier_key, {})
                tiers_info.append({
                    "tier": tier_num,
                    "label": _TIER_LABELS[tier_num],
                    "total_jobs": t.get("total_jobs", 0),
                    "real_max_page": t.get("real_max_page", 0),
                    "visited_pages": len(t.get("visited_pages", [])),
                })
        else:
            # Old format (backward compat)
            visited_list = data.get("visited_pages", [])
            visited_pages = len(visited_list)
            visited_pages_list = sorted(visited_list)
            real_max_page = data.get("real_max_page", 0)
            max_collectable = min(real_max_page, 100) * 50 if real_max_page else 0
            tiers_info = []

        pct = round(min(collected / CHAOS_TARGET_PER_CAT * 100, 100), 1)
        total_collected += collected
        categories.append({
            "uid": uid,
            "name": _UID_TO_NAME.get(uid, uid),
            "collected": collected,
            "visited_pages": visited_pages,          # total across all tiers
            "visited_pages_list": visited_pages_list,
            "real_max_page": real_max_page,          # total across all tiers
            "total_upwork_jobs": total_upwork_jobs,
            "max_collectable": max_collectable,
            "pct": pct,
            "tiers": tiers_info,                     # per-tier breakdown
        })

    # Sort by name for consistent display
    categories.sort(key=lambda c: c["name"])

    return {
        "target_per_cat": CHAOS_TARGET_PER_CAT,
        "state_file": str(CHAOS_STATE_PATH),
        "categories": categories,
        "total_collected": total_collected,
    }


# ---------------------------------------------------------------------------
# Schedule endpoints
# ---------------------------------------------------------------------------

CRONTAB_PATH = "/etc/cron.d/scraper-cron"
CRON_MARKER = "SCRAPER_AUTO"
CRON_CMD = "/app/scripts/chaos_runner.sh >> /var/log/scraper.log 2>&1"
CRON_USER = "root"  # cron.d format requires a username field


def _read_crontab() -> str:
    try:
        with open(CRONTAB_PATH) as f:
            return f.read()
    except FileNotFoundError:
        # fallback: read crontab for current user
        result = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True)
        return result.stdout if result.returncode == 0 else ""


def _write_crontab(content: str) -> None:
    try:
        with open(CRONTAB_PATH, "w") as f:
            f.write(content)
        subprocess.run(["chmod", "644", CRONTAB_PATH], check=True)
    except PermissionError:
        # fallback: use crontab command
        proc = subprocess.run(
            ["crontab", "-"], input=content, text=True, capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr)


def _parse_cron_line(line: str) -> dict | None:
    """Parse a cron line into components. Returns None if not a valid job.

    Handles both formats:
      - cron.d (7+ fields):  min hour dom month dow USERNAME command
      - user crontab (6 fields): min hour dom month dow command
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    # Try cron.d format first (7 fields including username)
    parts = line.split(None, 6)
    if len(parts) >= 7:
        return {
            "minute": parts[0],
            "hour": parts[1],
            "dom": parts[2],
            "month": parts[3],
            "dow": parts[4],
            # parts[5] is the username field (e.g. "root") – skip it
            "command": parts[6],
            "enabled": True,
        }
    # Fallback: user crontab format (6 fields)
    parts6 = line.split(None, 5)
    if len(parts6) >= 6:
        return {
            "minute": parts6[0],
            "hour": parts6[1],
            "dom": parts6[2],
            "month": parts6[3],
            "dow": parts6[4],
            "command": parts6[5],
            "enabled": True,
        }
    return None


def _build_cron_line(minute: str, hour: str, dom: str,
                     month: str, dow: str) -> str:
    return f"{minute} {hour} {dom} {month} {dow} {CRON_USER} {CRON_CMD}"


@app.get("/schedule")
def get_schedule() -> dict:
    """Return current cron schedule for the scraper."""
    content = _read_crontab()
    jobs = []
    enabled = False
    for line in content.splitlines():
        stripped = line.strip()
        # disabled line: "#! SCRAPER_AUTO 0 8-22 * * 1-6 root /app/scripts/..."
        if stripped.startswith("#!") and CRON_MARKER in stripped:
            raw = stripped[2:].strip()
            # strip the marker token so _parse_cron_line sees a clean cron line
            if raw.startswith(CRON_MARKER + " "):
                raw = raw[len(CRON_MARKER) + 1:]
            parsed = _parse_cron_line(raw)
            if parsed:
                parsed["enabled"] = False
                jobs.append(parsed)
        elif not stripped.startswith("#") and CRON_CMD in stripped:
            parsed = _parse_cron_line(stripped)
            if parsed:
                parsed["enabled"] = True
                enabled = True
                jobs.append(parsed)

    # If no marker found, return current active cron lines with the command
    if not jobs:
        for line in content.splitlines():
            if CRON_CMD in line and not line.strip().startswith("#"):
                parsed = _parse_cron_line(line)
                if parsed:
                    parsed["enabled"] = True
                    enabled = True
                    jobs.append(parsed)

    return {
        "enabled": enabled,
        "jobs": jobs,
        "raw": content,
    }


class ScheduleSetRequest(BaseModel):
    minute: str = "0"
    hour: str = "8-22"
    dom: str = "*"
    month: str = "*"
    dow: str = "1-6"
    enabled: bool = True


@app.post("/schedule", dependencies=[Depends(require_api_key)])
def set_schedule(req: ScheduleSetRequest) -> dict:
    """Set a new cron schedule for the scraper."""
    content = _read_crontab()
    new_line = _build_cron_line(
        req.minute, req.hour, req.dom, req.month, req.dow)
    if not req.enabled:
        new_line = f"#! {CRON_MARKER} {new_line}"

    # Remove existing scraper lines (active and disabled)
    lines = []
    for line in content.splitlines():
        if CRON_CMD in line:
            continue
        lines.append(line)

    # Strip trailing blank lines and add new entry
    while lines and not lines[-1].strip():
        lines.pop()
    lines.append(f"# {CRON_MARKER}")
    lines.append(new_line)
    lines.append("")

    try:
        _write_crontab("\n".join(lines))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    log.info("Cron schedule updated: %s", new_line)
    return {"ok": True, "line": new_line, "enabled": req.enabled}


@app.post("/schedule/enable", dependencies=[Depends(require_api_key)])
def enable_schedule() -> dict:
    """Enable the cron schedule (uncomment existing line)."""
    content = _read_crontab()
    lines = []
    changed = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#!") and CRON_CMD in stripped:
            raw = stripped[2:].strip()
            # strip the marker token so the restored line is a valid cron entry
            if raw.startswith(CRON_MARKER + " "):
                raw = raw[len(CRON_MARKER) + 1:]
            lines.append(raw)
            changed = True
        else:
            lines.append(line)
    if not changed:
        raise HTTPException(
            status_code=404,
            detail="No disabled schedule found. Use POST /schedule to set one.")
    try:
        _write_crontab("\n".join(lines))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"ok": True, "message": "Cron schedule enabled."}


@app.post("/schedule/disable", dependencies=[Depends(require_api_key)])
def disable_schedule() -> dict:
    """Disable the cron schedule (comment out the line)."""
    content = _read_crontab()
    lines = []
    changed = False
    for line in content.splitlines():
        stripped = line.strip()
        if CRON_CMD in stripped and not stripped.startswith("#"):
            lines.append(f"#! {CRON_MARKER} {stripped}")
            changed = True
        else:
            lines.append(line)
    if not changed:
        raise HTTPException(
            status_code=404, detail="No active schedule found.")
    try:
        _write_crontab("\n".join(lines))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"ok": True, "message": "Cron schedule disabled."}
