"""
Dashboard API — FastAPI service running on port 8003.

Responsibilities Day 2:
  - Serve live inventory alerts, forecast alerts, proposals, stats
  - Handle approve/reject actions (DB only — LangGraph resume on Day 4)

Responsibilities added Day 3:
  - APScheduler background jobs:
      * every 60s:  inventory_monitor — auto-create proposals for violations
      * every 5min: forecast_monitor  — auto-create forecast_tuning proposals

Why lifespan instead of @app.on_event("startup")?
FastAPI deprecated on_event in favour of the lifespan context manager.
lifespan gives us a clean place to open AND close resources — if we
don't close the pool and scheduler, connections leak and threads hang.
"""
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import create_pool
from monitor import (
    inventory_monitor,
    forecast_monitor,
    make_sync_job,
    INVENTORY_CHECK_INTERVAL,
    FORECAST_CHECK_INTERVAL,
)
from routers import inventory, forecast, proposals, stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────
    app.state.db = await create_pool()
    logger.info("✓ Database pool created")

    # ── APScheduler setup ─────────────────────────────────────
    # BackgroundScheduler runs jobs in a thread pool alongside FastAPI.
    # We pass the DB pool into each job via closure (make_sync_job).
    scheduler = BackgroundScheduler(
        job_defaults={"misfire_grace_time": 30},  # allow 30s late start
    )

    scheduler.add_job(
        make_sync_job(inventory_monitor),
        trigger="interval",
        seconds=INVENTORY_CHECK_INTERVAL,
        id="inventory_monitor",
        name="Inventory violation scanner",
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=5),
    )

    scheduler.add_job(
        make_sync_job(forecast_monitor),
        trigger="interval",
        seconds=FORECAST_CHECK_INTERVAL,
        id="forecast_monitor",
        name="MAPE threshold scanner",
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=10),
    )

    scheduler.start()
    app.state.scheduler = scheduler
    logger.info(
        f"✓ APScheduler started — "
        f"inventory scan every {INVENTORY_CHECK_INTERVAL}s, "
        f"MAPE scan every {FORECAST_CHECK_INTERVAL}s"
    )

    yield  # ← FastAPI serves requests between startup and shutdown

    # ── Shutdown ──────────────────────────────────────────────
    scheduler.shutdown(wait=False)
    logger.info("✓ APScheduler stopped")
    await app.state.db.close()
    logger.info("✓ Database pool closed")


app = FastAPI(
    title="Supply Chain AI — Dashboard API",
    version="0.3.0",
    description="Real-time inventory, forecast, and proposal management for CVS Health supply chain ops.",
    lifespan=lifespan,
)

# CORS: allow the Next.js dev server (port 3000) and prod domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
PREFIX = "/api/dashboard"
app.include_router(inventory.router, prefix=PREFIX, tags=["inventory"])
app.include_router(forecast.router,  prefix=PREFIX, tags=["forecast"])
app.include_router(proposals.router, prefix=PREFIX, tags=["proposals"])
app.include_router(stats.router,     prefix=PREFIX, tags=["stats"])


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "dashboard_api"}


@app.get("/api/dashboard/monitor/status")
async def monitor_status():
    """
    Returns current scheduler job states.
    Useful for debugging — hit this to see when jobs last ran / next run.
    """
    scheduler: BackgroundScheduler = app.state.scheduler
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id":        job.id,
            "name":      job.name,
            "next_run":  str(job.next_run_time),
        })
    return {"scheduler": "running" if scheduler.running else "stopped", "jobs": jobs}
