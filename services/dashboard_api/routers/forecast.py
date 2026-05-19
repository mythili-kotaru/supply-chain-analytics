"""
GET /forecast/alerts

Returns forecast_metrics rows where MAPE exceeds the 15% threshold.
Ordered by mape_pct DESC so the worst-performing models surface first
in the ForecastPanel.

The hyperparameters column is stored as JSONB in Postgres — asyncpg
returns it as a Python dict automatically, so no manual JSON parsing needed.
"""
import json
from fastapi import APIRouter, Depends
import asyncpg
from database import get_db
from models import ForecastAlert

router = APIRouter()

MAPE_THRESHOLD = 15.0  # percent — matches the ForecastPanel threshold marker


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
