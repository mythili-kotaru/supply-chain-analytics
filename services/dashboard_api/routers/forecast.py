"""
GET /forecast/alerts          — MAPE violations above threshold
GET /forecast/drift           — Hyperparameter tuning outcomes (drift detection)
GET /forecast/drift/{product} — Drift history for a specific product

Returns forecast_metrics rows where MAPE exceeds the 15% threshold.
Ordered by mape_pct DESC so the worst-performing models surface first
in the ForecastPanel.

The hyperparameters column is stored as JSONB in Postgres — asyncpg
returns it as a Python dict automatically, so no manual JSON parsing needed.

Day 7 — Drift Detection:
After a hyperparameter tuning is approved and executed, the supervisor
inserts a new forecast_metrics row with a simulated post-tuning MAPE.
The drift endpoints expose this data so the dashboard can show whether
the tuning actually improved the model.
"""
import json
from typing import Optional
from fastapi import APIRouter, Depends
import asyncpg
from database import get_db
from models import ForecastAlert

router = APIRouter()

MAPE_THRESHOLD = 15.0  # percent — matches the ForecastPanel threshold marker


def _parse_jsonb(val):
    """Safely parse a JSONB value from asyncpg — handles str, dict, or Record."""
    if val is None:
        return {}
    if isinstance(val, str):
        return json.loads(val)
    if isinstance(val, dict):
        return val
    try:
        return dict(val)
    except Exception:
        return json.loads(str(val))


@router.get("/forecast/alerts", response_model=list[ForecastAlert])
async def get_forecast_alerts(db: asyncpg.Pool = Depends(get_db)):
    rows = await db.fetch("""
        SELECT
            fm.product_id,
            p.product_name,
            fm.model_name,
            (fm.mape * 100)::numeric(6,2) AS mape_pct,
            fm.run_date::text             AS run_date,
            fm.notes,
            fm.hyperparameters
        FROM forecast_metrics fm
        JOIN products p ON p.product_id = fm.product_id
        WHERE fm.mape * 100 > $1
        ORDER BY fm.mape DESC
    """, MAPE_THRESHOLD)

    return [
        ForecastAlert(
            product_id=row["product_id"],
            product_name=row["product_name"],
            model_name=row["model_name"],
            mape_pct=float(row["mape_pct"]),
            run_date=row["run_date"],
            notes=row["notes"] or "",
            hyperparameters=(json.loads(row["hyperparameters"]) if isinstance(row["hyperparameters"], str) else dict(row["hyperparameters"])) if row["hyperparameters"] else {},
        )
        for row in rows
    ]


@router.get("/forecast/drift")
async def get_drift_summary(db: asyncpg.Pool = Depends(get_db)):
    """
    Day 7: Return all hyperparameter tuning outcomes with drift metrics.
    Shows pre_mape, post_mape, mape_delta, and whether the tuning helped.
    """
    rows = await db.fetch("""
        SELECT
            htl.id,
            htl.product_id,
            p.product_name,
            htl.old_params,
            htl.new_params,
            htl.rationale,
            htl.status,
            htl.pre_mape,
            htl.post_mape,
            htl.mape_delta,
            htl.simulated,
            htl.evaluated_at,
            htl.proposed_at
        FROM hyperparameter_tuning_log htl
        JOIN products p ON p.product_id = htl.product_id
        ORDER BY htl.proposed_at DESC
        LIMIT 50
    """)

    def _parse_jsonb(val):
        if val is None:
            return {}
        if isinstance(val, str):
            return json.loads(val)
        if isinstance(val, dict):
            return val
        return dict(val)

    results = []
    for row in rows:
        pre = float(row["pre_mape"]) if row["pre_mape"] is not None else None
        post = float(row["post_mape"]) if row["post_mape"] is not None else None
        delta = float(row["mape_delta"]) if row["mape_delta"] is not None else None

        results.append({
            "id": row["id"],
            "product_id": row["product_id"],
            "product_name": row["product_name"],
            "status": row["status"],
            "old_params": _parse_jsonb(row["old_params"]),
            "new_params": _parse_jsonb(row["new_params"]),
            "rationale": row["rationale"] or "",
            "pre_mape_pct": round(pre * 100, 2) if pre else None,
            "post_mape_pct": round(post * 100, 2) if post else None,
            "mape_delta_pct": round(delta * 100, 2) if delta else None,
            "improved": delta > 0 if delta is not None else None,
            "simulated": row["simulated"],
            "evaluated_at": row["evaluated_at"].isoformat() if row["evaluated_at"] else None,
            "proposed_at": row["proposed_at"].isoformat() if row["proposed_at"] else None,
        })

    return results


@router.get("/forecast/drift/{product_id}")
async def get_drift_for_product(product_id: str, db: asyncpg.Pool = Depends(get_db)):
    """
    Day 7: Return MAPE history for a specific product — useful for charting
    how the model has improved over successive tuning rounds.
    """
    rows = await db.fetch("""
        SELECT
            run_date::text AS run_date,
            (mape * 100)::numeric(6,2) AS mape_pct,
            notes,
            hyperparameters
        FROM forecast_metrics
        WHERE product_id = $1
        ORDER BY run_date ASC
    """, product_id)

    return {
        "product_id": product_id,
        "history": [
            {
                "run_date": row["run_date"],
                "mape_pct": float(row["mape_pct"]),
                "notes": row["notes"] or "",
                "hyperparameters": _parse_jsonb(row["hyperparameters"]),
            }
            for row in rows
        ]
    }
