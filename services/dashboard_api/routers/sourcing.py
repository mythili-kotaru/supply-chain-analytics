"""
routers/sourcing.py
───────────────────
FastAPI APIRouter for Supplier Performance and Sourcing optimization metrics.
Calculates actual average lead times, costs, and delivery reliability from supply_chain_records.
"""
from fastapi import APIRouter, Depends, HTTPException
import asyncpg
from typing import Optional
from pydantic import BaseModel

from database import get_db

router = APIRouter()

class SupplierScorecardItem(BaseModel):
    supplier_id: str
    supplier_name: str
    location: Optional[str] = None
    default_lead_time: int
    declared_defect_rate: float
    total_orders: int
    avg_delivery_days: Optional[float] = None
    avg_lead_time_drift: Optional[float] = None
    avg_unit_manufacturing_cost: Optional[float] = None
    avg_unit_shipping_cost: Optional[float] = None
    on_time_delivery_pct: Optional[float] = None
    risk_score: float


def calculate_risk_score(on_time_pct: Optional[float], lead_drift: Optional[float], defect_rate: float) -> float:
    # 1. Defect rate risk: 5% defect rate = 30 points max
    defect_risk = min((float(defect_rate) / 0.05) * 30, 30.0)
    
    # 2. On-time delivery risk: 100% on-time = 0 risk, 50% on-time = 25 risk, 0% on-time = 50 risk
    on_time_val = on_time_pct if on_time_pct is not None else 100.0
    on_time_risk = ((100.0 - on_time_val) / 100.0) * 50.0
    
    # 3. Lead time drift risk: 0 drift = 0 risk, 5 days late = 20 risk max
    drift_val = lead_drift if lead_drift is not None else 0.0
    drift_risk = max(min((drift_val / 5.0) * 20.0, 20.0), 0.0)
    
    return round(defect_risk + on_time_risk + drift_risk, 1)


@router.get("/sourcing/scorecard", response_model=list[SupplierScorecardItem])
async def get_sourcing_scorecard(db: asyncpg.Pool = Depends(get_db)):
    """
    Get aggregated performance scorecards for all suppliers.
    """
    query = """
        SELECT
            s.supplier_id,
            s.supplier_name,
            s.location,
            s.lead_time_days AS default_lead_time,
            s.defect_rate AS declared_defect_rate,
            COUNT(scr.record_id) AS total_orders,
            ROUND(AVG(scr.delivery_date - scr.order_date), 1) AS avg_delivery_days,
            ROUND(AVG((scr.delivery_date - scr.order_date) - s.lead_time_days), 1) AS avg_lead_time_drift,
            ROUND(AVG(scr.manufacturing_costs / NULLIF(scr.order_quantity, 0)), 2) AS avg_unit_manufacturing_cost,
            ROUND(AVG(scr.shipping_costs / NULLIF(scr.order_quantity, 0)), 2) AS avg_unit_shipping_cost,
            ROUND(
                (COUNT(CASE WHEN (scr.delivery_date - scr.order_date) <= s.lead_time_days THEN 1 END)::numeric / 
                 NULLIF(COUNT(scr.record_id), 0)) * 100,
                1
            ) AS on_time_delivery_pct
        FROM suppliers s
        LEFT JOIN supply_chain_records scr ON s.supplier_id = scr.supplier_id
        GROUP BY s.supplier_id, s.supplier_name, s.lead_time_days, s.defect_rate, s.location
        ORDER BY s.supplier_id ASC
    """
    try:
        rows = await db.fetch(query)
        results = []
        for r in rows:
            on_time = float(r["on_time_delivery_pct"]) if r["on_time_delivery_pct"] is not None else None
            drift = float(r["avg_lead_time_drift"]) if r["avg_lead_time_drift"] is not None else None
            defect = float(r["declared_defect_rate"])
            
            risk = calculate_risk_score(on_time, drift, defect)
            
            results.append(
                SupplierScorecardItem(
                    supplier_id=r["supplier_id"],
                    supplier_name=r["supplier_name"],
                    location=r["location"],
                    default_lead_time=r["default_lead_time"],
                    declared_defect_rate=defect,
                    total_orders=r["total_orders"],
                    avg_delivery_days=float(r["avg_delivery_days"]) if r["avg_delivery_days"] is not None else None,
                    avg_lead_time_drift=drift,
                    avg_unit_manufacturing_cost=float(r["avg_unit_manufacturing_cost"]) if r["avg_unit_manufacturing_cost"] is not None else None,
                    avg_unit_shipping_cost=float(r["avg_unit_shipping_cost"]) if r["avg_unit_shipping_cost"] is not None else None,
                    on_time_delivery_pct=on_time,
                    risk_score=risk
                )
            )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sourcing database query failed: {str(e)}")


@router.get("/sourcing/scorecard/{supplier_id}", response_model=SupplierScorecardItem)
async def get_supplier_scorecard(supplier_id: str, db: asyncpg.Pool = Depends(get_db)):
    """
    Get scorecard details for a single supplier.
    """
    scorecard = await get_sourcing_scorecard(db)
    for s in scorecard:
        if s.supplier_id == supplier_id:
            return s
    raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found.")
