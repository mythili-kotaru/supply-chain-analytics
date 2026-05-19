"""
Dashboard API — FastAPI service running on port 8003.

Responsibilities today (Day 2):
  - Serve live inventory alerts, forecast alerts, proposals, and stats
  - Handle approve/reject actions (DB only — LangGraph resume on Day 4)

Responsibilities added Day 3:
  - APScheduler background jobs:
      * every 60s: scan inventory, auto-create proposals for new violations
      * every 5min: scan MAPE, auto-create forecast_tuning proposals

Why lifespan instead of @app.on_event("startup")?
FastAPI deprecated on_event in favour of the lifespan context manager.
lifespan gives us a clean place to open AND close the DB pool — if we
don't close the pool, connections leak and Postgres eventually refuses
new connections.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import create_pool
from routers import inventory, forecast, proposals, stats


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────
    app.state.db = await create_pool()
    print("✓ Database pool created")
    yield
    # ── Shutdown ─────────────────────────────────────────────
    await app.state.db.close()
    print("✓ Database pool closed")


app = FastAPI(
    title="Supply Chain AI — Dashboard API",
    version="0.2.0",
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

# Register routers — all routes live under /api/dashboard prefix
PREFIX = "/api/dashboard"
app.include_router(inventory.router, prefix=PREFIX, tags=["inventory"])
app.include_router(forecast.router,  prefix=PREFIX, tags=["forecast"])
app.include_router(proposals.router, prefix=PREFIX, tags=["proposals"])
app.include_router(stats.router,     prefix=PREFIX, tags=["stats"])


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "dashboard_api"}
