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
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from auth import get_current_user, get_current_role

from database import create_pool
from monitor import (
    inventory_monitor,
    forecast_monitor,
    anomaly_monitor,
    make_sync_job,
    INVENTORY_CHECK_INTERVAL,
    FORECAST_CHECK_INTERVAL,
    ANOMALY_CHECK_INTERVAL,
)
from routers import inventory, forecast, proposals, stats, anomaly, analytics, charts, auth, sourcing, simulation, chaos

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

    # Create users table and seed default credentials
    async with app.state.db.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'analyst',
                full_name VARCHAR(100) NOT NULL
            );
        """)
        
        count = await conn.fetchval("SELECT COUNT(*) FROM users")
        if count == 0:
            from auth import hash_password
            analyst_hash = hash_password("mythili123")
            await conn.execute("""
                INSERT INTO users (username, password_hash, role, full_name)
                VALUES ('mythili', $1, 'analyst', 'Mythili Kotaru')
            """, analyst_hash)
            
            admin_hash = hash_password("admin123")
            await conn.execute("""
                INSERT INTO users (username, password_hash, role, full_name)
                VALUES ('admin', $1, 'admin', 'Ops Administrator')
            """, admin_hash)
            logger.info("✓ Seeded default analyst & admin credentials in users table")

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

    scheduler.add_job(
        make_sync_job(anomaly_monitor),
        trigger="interval",
        seconds=ANOMALY_CHECK_INTERVAL,
        id="anomaly_monitor",
        name="Anomaly detection scanner",
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=15),
    )

    scheduler.start()
    app.state.scheduler = scheduler
    logger.info(
        f"✓ APScheduler started — "
        f"inventory scan every {INVENTORY_CHECK_INTERVAL}s, "
        f"MAPE scan every {FORECAST_CHECK_INTERVAL}s, "
        f"anomaly scan every {ANOMALY_CHECK_INTERVAL}s"
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

import time
from fastapi import Request

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """
    Middleware to log and inject X-Process-Time header for observability.
    """
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    logger.info(f"REQ: {request.method} {request.url.path} - {process_time:.4f}s")
    return response

# Register routers
PREFIX = "/api/dashboard"
app.include_router(auth.router,      prefix=PREFIX, tags=["auth"])
app.include_router(inventory.router, prefix=PREFIX, tags=["inventory"], dependencies=[Depends(get_current_user)])
app.include_router(forecast.router,  prefix=PREFIX, tags=["forecast"], dependencies=[Depends(get_current_user)])
app.include_router(proposals.router, prefix=PREFIX, tags=["proposals"], dependencies=[Depends(get_current_user)])
app.include_router(proposals.slack_router, prefix=PREFIX, tags=["slack"])
app.include_router(stats.router,     prefix=PREFIX, tags=["stats"], dependencies=[Depends(get_current_user)])
app.include_router(anomaly.router,   prefix=PREFIX, tags=["anomaly"], dependencies=[Depends(get_current_user)])
app.include_router(analytics.router, prefix=PREFIX + "/analytics", tags=["analytics"], dependencies=[Depends(get_current_user)])
app.include_router(charts.router,    prefix=PREFIX, tags=["charts"], dependencies=[Depends(get_current_user)])
app.include_router(sourcing.router,  prefix=PREFIX, tags=["sourcing"], dependencies=[Depends(get_current_user)])
app.include_router(simulation.router, prefix=PREFIX, tags=["simulation"], dependencies=[Depends(get_current_user)])
app.include_router(chaos.router,     prefix=PREFIX, tags=["chaos"], dependencies=[Depends(get_current_user)])



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


@app.post("/api/dashboard/monitor/run")
async def trigger_monitor_run(role: str = Depends(get_current_role)):
    """
    Manually triggers all background monitors immediately.
    Useful for on-demand agent scans from the UI.
    """
    if role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied: Only administrator role can trigger manual monitor runs.")
    db = app.state.db
    results = {}
    try:
        await inventory_monitor(db)
        results["inventory_monitor"] = "ok"
    except Exception as e:
        results["inventory_monitor"] = f"error: {e}"
    try:
        await forecast_monitor(db)
        results["forecast_monitor"] = "ok"
    except Exception as e:
        results["forecast_monitor"] = f"error: {e}"
    try:
        await anomaly_monitor(db)
        results["anomaly_monitor"] = "ok"
    except Exception as e:
        results["anomaly_monitor"] = f"error: {e}"

    return {"status": "triggered", "results": results}
