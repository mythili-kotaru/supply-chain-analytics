"""
services/replenishment_agent/main.py
──────────────────────────────────────
Replenishment Agent — computes purchase orders for stockout-risk products.

WHAT DOES REPLENISHMENT DO?
Different from allocation (moving existing stock between locations):
  Replenishment = ordering NEW stock from suppliers.

Algorithm:
  1. Find products where stock < reorder_point (stockout risk)
  2. For each, find the best supplier (lowest lead time + lowest defect rate)
  3. Compute order quantity: max_capacity - current_stock (fill to max)
  4. Generate a purchase order draft

WHY SEPARATE FROM ALLOCATION?
  - Different stakeholder: allocation is a warehouse ops decision,
    replenishment is a procurement decision
  - Different data: allocation reads internal inventory,
    replenishment reads supplier lead times and defect rates
  - Different urgency: allocation is tactical (days),
    replenishment is strategic (weeks, considering lead times)
"""

import asyncio
import uuid
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, Any

import asyncpg
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://scai:scai_password@localhost:5432/supply_chain")

import json

async def db_create_task(db: asyncpg.Pool, task_id: str, product_id: str | None, task_input: dict):
    async with db.acquire() as conn:
        await conn.execute("""
            INSERT INTO replenishment_tasks (task_id, product_id, status, created_at, input_payload, result_payload, error)
            VALUES ($1, $2, 'pending', NOW(), $3, NULL, NULL)
        """, task_id, product_id, json.dumps(task_input))

async def db_get_task(db: asyncpg.Pool, task_id: str) -> dict | None:
    async with db.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT task_id, status, created_at, input_payload, result_payload, error
            FROM replenishment_tasks
            WHERE task_id = $1
        """, task_id)
        if not row:
            return None
        
        input_payload = row["input_payload"]
        if isinstance(input_payload, str):
            input_payload = json.loads(input_payload)
        elif input_payload is None:
            input_payload = {}
            
        result_payload = row["result_payload"]
        if isinstance(result_payload, str):
            result_payload = json.loads(result_payload)
            
        return {
            "task_id": row["task_id"],
            "status": row["status"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "input": input_payload,
            "result": result_payload,
            "error": row["error"]
        }

async def db_update_task_status(db: asyncpg.Pool, task_id: str, status: str, result: dict | None = None, error: str | None = None):
    async with db.acquire() as conn:
        if result is not None:
            await conn.execute("""
                UPDATE replenishment_tasks
                SET status = $1, result_payload = $2, error = NULL
                WHERE task_id = $3
            """, status, json.dumps(result), task_id)
        elif error is not None:
            await conn.execute("""
                UPDATE replenishment_tasks
                SET status = $1, error = $2, result_payload = NULL
                WHERE task_id = $3
            """, status, error, task_id)
        else:
            await conn.execute("""
                UPDATE replenishment_tasks
                SET status = $1
                WHERE task_id = $2
            """, status, task_id)



@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    logger.info("✓ Replenishment agent DB pool created")
    yield
    await app.state.db.close()
    logger.info("✓ Replenishment agent DB pool closed")


app = FastAPI(
    title="Replenishment Agent",
    description="A2A agent for generating purchase order recommendations",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/agent-card")
async def agent_card():
    return {
        "name": "Replenishment Agent",
        "version": "1.0.0",
        "description": "Generates purchase order drafts for stockout-risk products",
        "capabilities": ["replenishment_planning", "purchase_order_generation"],
        "input_schema": {
            "product_id": "optional — filter to specific product",
            "role": "string"
        },
        "output_schema": {
            "purchase_orders": "list of PO drafts per product/supplier",
            "summary": "human-readable summary",
            "total_order_value": "float — estimated total cost"
        }
    }


class ReplenishmentTaskInput(BaseModel):
    task_id: str
    type: str
    product_id: str | None = None
    role: str = "analyst"
    requested_at: str = ""


@app.post("/tasks")
async def create_task(task_input: ReplenishmentTaskInput, background_tasks: BackgroundTasks):
    task_id = task_input.task_id or str(uuid.uuid4())
    db = app.state.db
    
    # Initialize task state in DB
    await db_create_task(db, task_id, task_input.product_id, task_input.model_dump())
    
    background_tasks.add_task(
        compute_replenishment,
        task_id=task_id,
        product_id=task_input.product_id
    )
    return {"task_id": task_id, "status": "pending"}


@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    db = app.state.db
    task = await db_get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


async def compute_replenishment(task_id: str, product_id: str | None):
    """Compute purchase orders for all products below reorder point."""
    db = app.state.db
    await db_update_task_status(db, task_id, "in_progress")

    try:
        pool = app.state.db
        async with pool.acquire() as conn:

            # Get products at stockout risk
            product_filter = "AND i.product_id = $1" if product_id else ""
            params = [product_id] if product_id else []

            at_risk = await conn.fetch(f"""
                SELECT
                    i.product_id,
                    p.product_name,
                    p.price,
                    i.location,
                    i.stock_level,
                    i.reorder_point,
                    i.max_capacity,
                    i.max_capacity - i.stock_level AS units_to_order
                FROM inventory i
                JOIN products p ON i.product_id = p.product_id
                WHERE i.stock_level < i.reorder_point
                {product_filter}
                ORDER BY (i.reorder_point - i.stock_level) DESC
            """, *params)

            # Get best supplier per product (lowest lead time, then lowest defect rate)
            suppliers = await conn.fetch("""
                SELECT supplier_id, supplier_name, location, lead_time_days, defect_rate
                FROM suppliers
                ORDER BY lead_time_days ASC, defect_rate ASC
            """)

        best_supplier = dict(suppliers[0]) if suppliers else {
            "supplier_id": "SUP-001",
            "supplier_name": "Default Supplier",
            "location": "Unknown",
            "lead_time_days": 14,
            "defect_rate": 0.02
        }

        purchase_orders = []
        total_order_value = 0.0

        for row in at_risk:
            units = int(row["units_to_order"])
            unit_price = float(row["price"])
            order_value = units * unit_price
            expected_delivery = (datetime.utcnow() + timedelta(days=best_supplier["lead_time_days"])).date()

            purchase_orders.append({
                "po_number": f"PO-{uuid.uuid4().hex[:8].upper()}",
                "product_id": row["product_id"],
                "product_name": row["product_name"],
                "location": row["location"],
                "current_stock": row["stock_level"],
                "reorder_point": row["reorder_point"],
                "order_quantity": units,
                "unit_price": unit_price,
                "order_value": round(order_value, 2),
                "supplier_id": best_supplier["supplier_id"],
                "supplier_name": best_supplier["supplier_name"],
                "lead_time_days": best_supplier["lead_time_days"],
                "expected_delivery": str(expected_delivery),
                "status": "draft"
            })
            total_order_value += order_value

        summary = (
            f"Generated {len(purchase_orders)} purchase order(s) for "
            f"{len(at_risk)} stockout-risk location(s). "
            f"Total estimated value: ${total_order_value:,.2f}. "
            f"Using supplier: {best_supplier['supplier_name']} "
            f"(lead time: {best_supplier['lead_time_days']} days)."
        )

        result_data = {
            "purchase_orders": purchase_orders,
            "summary": summary,
            "total_order_value": round(total_order_value, 2),
            "completed_at": datetime.utcnow().isoformat()
        }
        await db_update_task_status(db, task_id, "completed", result=result_data)

    except Exception as e:
        logger.error(f"Replenishment task {task_id} failed: {e}")
        await db_update_task_status(db, task_id, "failed", error=str(e))


# ─────────────────────────────────────────────
# POST /tasks/{task_id}/execute
#
# Day 6: Insert approved purchase orders into the purchase_orders table
# and update inventory stock_level to reflect incoming stock.
#
# WHY update stock_level immediately and not after lead time?
# In a real system you'd schedule a future update based on expected_delivery.
# For this demo we apply it immediately so the dashboard reflects the change.
# ─────────────────────────────────────────────
class ExecuteDirectRequest(BaseModel):
    """
    Allows the supervisor to pass purchase orders directly from graph state.
    Used when the in-memory task store has been cleared (e.g. after service restart).
    """
    purchase_orders: list[dict]
    proposal_id: str | None = None


@app.post("/execute-direct")
async def execute_direct(req: ExecuteDirectRequest):
    """
    Execute purchase orders passed directly in the request body.
    Called by the supervisor when the task_id is no longer in memory.
    """
    return await _apply_purchase_orders(req.purchase_orders, req.proposal_id)


@app.post("/tasks/{task_id}/execute")
async def execute_task(task_id: str, proposal_id: str | None = None):
    """
    Persist approved purchase orders to the DB and update inventory levels.
    """
    db = app.state.db
    task = await db_get_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if task["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Task {task_id} is not completed (status={task['status']})"
        )

    result = task.get("result", {})
    purchase_orders = result.get("purchase_orders", [])

    if not purchase_orders:
        return {"executed": 0, "message": "No purchase orders to apply."}

    execution_result = await _apply_purchase_orders(purchase_orders, proposal_id)
    await db_update_task_status(db, task_id, "executed")
    return execution_result


async def _apply_purchase_orders(purchase_orders: list, proposal_id: str | None = None) -> dict:
    """
    Core DB logic: create purchase_orders table if needed, insert POs,
    and update inventory stock levels to max_capacity.
    Shared by both /tasks/{id}/execute and /execute-direct.
    """
    if not purchase_orders:
        return {"executed": 0, "message": "No purchase orders to apply."}

    import httpx
    jira_url = os.getenv("JIRA_API_URL")
    if not jira_url:
        jira_url = "http://dashboard_api:8003/api/dashboard/jira/mock-ticket"

    executed = 0
    errors = []

    pool = app.state.db
    async with pool.acquire() as conn:
        # Ensure purchase_orders table exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id              SERIAL PRIMARY KEY,
                po_number       TEXT UNIQUE NOT NULL,
                product_id      TEXT REFERENCES products(product_id),
                product_name    TEXT NOT NULL,
                location        TEXT NOT NULL,
                supplier_id     TEXT,
                supplier_name   TEXT,
                order_quantity  INTEGER NOT NULL,
                unit_price      NUMERIC(10,2),
                order_value     NUMERIC(12,2),
                lead_time_days  INTEGER,
                expected_delivery DATE,
                status          TEXT DEFAULT 'approved',
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                jira_ticket_key TEXT
            )
        """)

        # Dynamically add jira_ticket_key column if not exists
        await conn.execute("""
            ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS jira_ticket_key TEXT;
        """)

        for po in purchase_orders:
            try:
                # Coerce expected_delivery to a date object if it came in as a string
                expected_delivery = po["expected_delivery"]
                if isinstance(expected_delivery, str):
                    from datetime import date as _date
                    expected_delivery = _date.fromisoformat(expected_delivery)

                # Create Jira ticket for this PO
                jira_ticket_key = None
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        po_summary = f"[Purchase Order] {po['po_number']} approved for {po['product_name']} ({po['product_id']}) @ {po['location']}"
                        po_desc = (
                            f"Purchase Order Details:\n"
                            f"- PO Number: {po['po_number']}\n"
                            f"- Product: {po['product_name']} ({po['product_id']})\n"
                            f"- Location: {po['location']}\n"
                            f"- Order Quantity: {po['order_quantity']} units\n"
                            f"- Unit Price: ${po['unit_price']:.2f}\n"
                            f"- Total Value: ${po['order_value']:.2f}\n"
                            f"- Supplier: {po['supplier_name']} ({po['supplier_id']})\n"
                            f"- Expected Delivery: {po['expected_delivery']}"
                        )
                        jira_payload = {
                            "summary": po_summary,
                            "description": po_desc,
                            "project_key": "SC",
                            "issue_type": "Task",
                            "po_number": po["po_number"]
                        }
                        resp = await client.post(jira_url, json=jira_payload)
                        if resp.status_code in (200, 201):
                            resp_data = resp.json()
                            jira_ticket_key = resp_data.get("key")
                            po["jira_ticket_key"] = jira_ticket_key
                            logger.info(f"Successfully created Jira ticket {jira_ticket_key} for PO {po['po_number']}")
                        else:
                            logger.warning(f"Jira ticket creation returned status {resp.status_code}: {resp.text}")
                except Exception as jira_err:
                    logger.error(f"Failed to create Jira ticket for PO {po['po_number']}: {jira_err}")

                async with conn.transaction():
                    # Insert PO record
                    await conn.execute("""
                        INSERT INTO purchase_orders (
                            po_number, product_id, product_name, location,
                            supplier_id, supplier_name, order_quantity,
                            unit_price, order_value, lead_time_days,
                            expected_delivery, status, jira_ticket_key
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'approved',$12)
                        ON CONFLICT (po_number) DO UPDATE SET jira_ticket_key = EXCLUDED.jira_ticket_key
                    """,
                        po["po_number"], po["product_id"], po["product_name"],
                        po["location"], po["supplier_id"], po["supplier_name"],
                        po["order_quantity"], po["unit_price"], po["order_value"],
                        po["lead_time_days"], expected_delivery, jira_ticket_key
                    )

                    # Update inventory — fill to max_capacity
                    await conn.execute("""
                        UPDATE inventory
                        SET stock_level = max_capacity, last_updated = NOW()
                        WHERE product_id = $1 AND location = $2
                    """, po["product_id"], po["location"])

                    executed += 1
                    logger.info(
                        f"Executed PO {po['po_number']}: {po['order_quantity']} units "
                        f"of {po['product_id']} @ {po['location']}"
                    )
            except Exception as e:
                errors.append(f"{po['po_number']}: {str(e)}")
                logger.error(f"PO execution failed: {e}")

        # If proposal_id is provided, sync the jira_ticket_key back to the proposals table
        if proposal_id and executed > 0:
            try:
                row = await conn.fetchrow("SELECT replenishment_payload FROM proposals WHERE id = $1", proposal_id)
                if row and row["replenishment_payload"]:
                    payload = row["replenishment_payload"]
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                    po_list = payload.get("purchase_orders", [])
                    for p_order in po_list:
                        for po_exec in purchase_orders:
                            if p_order.get("po_number") == po_exec.get("po_number") and po_exec.get("jira_ticket_key"):
                                p_order["jira_ticket_key"] = po_exec["jira_ticket_key"]
                    
                    await conn.execute(
                        "UPDATE proposals SET replenishment_payload = $1::jsonb WHERE id = $2",
                        json.dumps(payload), proposal_id
                    )
                    logger.info(f"Synchronized Jira ticket keys back to proposals replenishment_payload for proposal {proposal_id}")
            except Exception as sync_err:
                logger.error(f"Failed to synchronize Jira ticket keys to proposals table: {sync_err}")

    return {
        "executed": executed,
        "errors": errors,
        "message": f"Placed {executed} purchase order(s). Inventory updated to max capacity."
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)
