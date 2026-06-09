"""
GET  /anomaly/events          — Recent anomaly detections (last 24h, unacknowledged first)
POST /anomaly/scan            — Trigger an immediate scan (for manual testing)
POST /anomaly/events/{id}/ack — Acknowledge (dismiss) an anomaly event

Day 9: Anomaly Detection API
The scheduler in langgraph_agent runs detect automatically every 5 minutes.
These endpoints expose the results to the dashboard and allow manual triggers.
"""

import os
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header
import asyncpg
from database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://scai:scai_password@localhost:5432/supply_chain")


@router.get("/anomaly/events")
async def get_anomaly_events(
    limit: int = 50,
    severity: Optional[str] = None,
    anomaly_type: Optional[str] = None,
    unacked_only: bool = False,
    db: asyncpg.Pool = Depends(get_db)
):
    """
    Return recent anomaly events, newest first.
    Unacknowledged events surface before acknowledged ones within the same time window.
    """
    conditions = ["1=1"]
    params = []
    idx = 1

    if severity:
        conditions.append(f"ae.severity = ${idx}")
        params.append(severity.upper())
        idx += 1

    if anomaly_type:
        conditions.append(f"ae.anomaly_type = ${idx}")
        params.append(anomaly_type)
        idx += 1

    if unacked_only:
        conditions.append("ae.acknowledged = FALSE")

    where = " AND ".join(conditions)

    rows = await db.fetch(f"""
        SELECT
            ae.id,
            ae.detected_at::text        AS detected_at,
            ae.anomaly_type,
            ae.severity,
            ae.product_id,
            p.product_name,
            ae.location,
            ae.metric_name,
            ae.metric_value::float      AS metric_value,
            ae.baseline_value::float    AS baseline_value,
            ae.deviation_pct::float     AS deviation_pct,
            ae.anomaly_score::float     AS anomaly_score,
            ae.description,
            ae.proposal_id,
            ae.acknowledged,
            ae.acknowledged_at::text    AS acknowledged_at
        FROM anomaly_events ae
        JOIN products p ON p.product_id = ae.product_id
        WHERE {where}
          AND ae.detected_at > NOW() - INTERVAL '24 hours'
        ORDER BY ae.acknowledged ASC, ae.severity DESC, ae.detected_at DESC
        LIMIT ${idx}
    """, *params, limit)

    return [dict(row) for row in rows]


@router.get("/anomaly/stats")
async def get_anomaly_stats(db: asyncpg.Pool = Depends(get_db)):
    """
    Summary counts for the dashboard header badges.
    Returns counts by severity and type for the last 24 hours.
    """
    rows = await db.fetch("""
        SELECT
            severity,
            anomaly_type,
            COUNT(*) AS count,
            SUM(CASE WHEN acknowledged = FALSE THEN 1 ELSE 0 END) AS unacked_count
        FROM anomaly_events
        WHERE detected_at > NOW() - INTERVAL '24 hours'
        GROUP BY severity, anomaly_type
        ORDER BY
            CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 ELSE 3 END,
            count DESC
    """)

    total_unacked = sum(r["unacked_count"] for r in rows)
    critical_unacked = sum(r["unacked_count"] for r in rows if r["severity"] == "CRITICAL")

    return {
        "total_unacked": total_unacked,
        "critical_unacked": critical_unacked,
        "by_type": [dict(r) for r in rows],
    }


@router.post("/anomaly/events/{event_id}/ack")
async def acknowledge_anomaly(
    event_id: int,
    db: asyncpg.Pool = Depends(get_db),
    x_role: str = Header("analyst"),
):
    """
    Mark an anomaly as acknowledged (dismissed by ops manager).
    Acknowledged anomalies still appear in the feed but are visually de-emphasised.
    """
    if x_role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied: Only administrator role can acknowledge anomalies.")
    result = await db.execute("""
        UPDATE anomaly_events
        SET acknowledged = TRUE, acknowledged_at = NOW()
        WHERE id = $1
    """, event_id)

    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail=f"Anomaly event {event_id} not found")

    return {"id": event_id, "acknowledged": True}


@router.post("/anomaly/scan")
async def trigger_scan(x_role: str = Header("analyst")):
    """
    Manually trigger an anomaly scan — useful for testing without waiting for the scheduler.
    Runs synchronously (in the background via asyncio) and returns a summary.
    """
    if x_role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied: Only administrator role can trigger manual scans.")
    import sys, pathlib
    # Ensure agents/ is importable
    _here = pathlib.Path(__file__).resolve()
    for candidate in _here.parents:
        if (candidate / "agents").is_dir():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            break

    try:
        from agents.anomaly_detector import run_anomaly_scan
        summary = await run_anomaly_scan(DATABASE_URL)
        return {"status": "ok", "summary": summary}
    except Exception as e:
        logger.error(f"Manual anomaly scan failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
