"""
routers/chaos.py
────────────────
Endpoints to manually trigger chaos simulations (demand shocks, supplier delays)
for testing and demonstration purposes.
"""
from fastapi import APIRouter, Depends, HTTPException
import asyncpg
import random
import logging

from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/chaos/demand-shock")
async def trigger_demand_shock(db: asyncpg.Pool = Depends(get_db)):
    """
    Manually injects a demand shock by dropping inventory for a random product.
    """
    try:
        rows = await db.fetch("SELECT id, product_id, stock_level, reorder_point FROM inventory WHERE stock_level > reorder_point")
        if not rows:
            return {"status": "skipped", "message": "All items are already critical or below reorder point."}
            
        target = random.choice(rows)
        new_stock = max(0, target['reorder_point'] - random.randint(1, 50))
        
        await db.execute("UPDATE inventory SET stock_level = $1 WHERE id = $2", new_stock, target['id'])
        msg = f"Chaos Monkey Strike! 🌪️ Dropped stock for {target['product_id']} from {target['stock_level']} to {new_stock}."
        logger.warning(msg)
        
        return {"status": "success", "message": msg, "product_id": target["product_id"]}
    except Exception as e:
        logger.error(f"Error injecting demand shock: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chaos/supplier-delay")
async def trigger_supplier_delay(db: asyncpg.Pool = Depends(get_db)):
    """
    Manually injects a supplier delay.
    """
    try:
        rows = await db.fetch("SELECT supplier_id, supplier_name, lead_time_days FROM suppliers")
        if not rows:
            return {"status": "skipped", "message": "No suppliers found."}
            
        target = random.choice(rows)
        delay_days = random.randint(2, 7)
        new_lead_time = target['lead_time_days'] + delay_days
        
        await db.execute("UPDATE suppliers SET lead_time_days = $1 WHERE supplier_id = $2", new_lead_time, target['supplier_id'])
        msg = f"Chaos Monkey Strike! 🌪️ Delayed supplier {target['supplier_name']} by {delay_days} days."
        logger.warning(msg)
        
        return {"status": "success", "message": msg, "supplier_id": target["supplier_id"], "new_lead_time": new_lead_time}
    except Exception as e:
        logger.error(f"Error injecting supplier delay: {e}")
        raise HTTPException(status_code=500, detail=str(e))
