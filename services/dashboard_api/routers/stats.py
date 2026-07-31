"""
GET /stats

Aggregates dashboard-level numbers in a single query batch.
This powers the StatsBar component at the top of the dashboard.

We run 4 queries in parallel using asyncio.gather() rather than
sequentially — each query is independent and this halves latency
on a cold connection.
"""
import asyncio
import httpx
from fastapi import APIRouter, Depends, Request
import asyncpg

from database import get_db
from models import DashboardStats, ServiceHealth

router = APIRouter()

# Internal service URLs — same Docker network
# We probe /health (or /agent-card for A2A services)
SERVICES = {
    "MCP Server":          "http://mcp_server:8000/health",
    "Allocation Agent":    "http://allocation_agent:8001/agent-card",
    "Replenishment Agent": "http://replenishment_agent:8002/agent-card",
    "LangGraph Agent":     "http://langgraph_agent:8004/health",   # Day 4
}


async def _check_service(name: str, url: str) -> ServiceHealth:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(url)
            status = "healthy" if r.status_code == 200 else "degraded"
    except Exception:
        status = "down"
    return ServiceHealth(name=name, status=status)


@router.get("/stats", response_model=DashboardStats)
async def get_stats(request: Request, db: asyncpg.Pool = Depends(get_db)):
    # Run DB queries + service health checks concurrently
    (
        critical_row,
        pending_row,
        approved_row,
        po_value_row,
        mape_row,
        supplier_row,
        *service_results,
    ) = await asyncio.gather(
        db.fetchrow("SELECT COUNT(*) AS n FROM inventory WHERE stock_level <= reorder_point"),
        db.fetchrow("SELECT COUNT(*) AS n FROM proposals WHERE status = 'pending'"),
        db.fetchrow("SELECT COUNT(*) AS n FROM proposals WHERE status = 'approved' AND updated_at::date = CURRENT_DATE"),
        db.fetchrow("""
            SELECT COALESCE(SUM((replenishment_payload->>'total_order_value')::numeric), 0) AS total
            FROM proposals
            WHERE status = 'pending' AND type = 'replenishment'
        """),
        db.fetchrow("SELECT ROUND((AVG(mape) * 100)::numeric, 2) AS avg FROM forecast_metrics"),
        db.fetchrow("SELECT COUNT(*) AS n FROM suppliers"),
        *[_check_service(name, url) for name, url in SERVICES.items()],
    )

    # Check APScheduler background monitor
    scheduler = request.app.state.scheduler
    scheduler_status = "healthy" if scheduler.running else "down"
    service_results.append(ServiceHealth(name="Background Monitors", status=scheduler_status))

    return DashboardStats(
        critical_alerts=critical_row["n"],
        pending_approvals=pending_row["n"],
        approved_today=approved_row["n"],
        po_value_pending=float(po_value_row["total"]),
        avg_mape=float(mape_row["avg"] or 0),
        total_suppliers=supplier_row["n"],
        services=service_results,
    )
