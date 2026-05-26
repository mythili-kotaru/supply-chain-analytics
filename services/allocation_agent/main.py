"""
services/allocation_agent/main.py
───────────────────────────────────
Allocation Agent — an independent FastAPI A2A service.

WHAT DOES THE ALLOCATION AGENT DO?
Given a product and region, it:
  1. Looks up current inventory across all locations (via MCP or direct DB)
  2. Identifies surplus locations (stock >> reorder_point)
  3. Identifies deficit locations (stock < reorder_point)
  4. Computes a transfer plan: move N units from surplus to deficit
  5. Returns the plan as a structured result

WHY IS THIS A SEPARATE SERVICE (not just a LangGraph node)?
In a real supply chain system:
  - The allocation team owns this logic and can deploy it independently
  - It might need different scaling characteristics (compute-heavy)
  - It might integrate with an ERP system that the other agents don't touch
  - A2A makes it independently testable with its own API spec

A2A ENDPOINTS:
  POST /tasks        → create a new task (returns task_id)
  GET  /tasks/{id}   → poll status (pending/in_progress/completed/failed)
  GET  /agent-card   → describes this agent's capabilities (A2A spec)

WHY in-memory task store?
  For demo purposes. In production: store tasks in Redis or Postgres.
"""

import asyncio
import uuid
import logging
import os
from datetime import datetime
from typing import Dict, Any

import asyncpg
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://scai:scai_password@localhost:5432/supply_chain")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000")

app = FastAPI(
    title="Allocation Agent",
    description="A2A agent for computing inventory allocation plans",
    version="1.0.0"
)

# In-memory task store: task_id → task_state
# In production: replace with Redis or Postgres
tasks: Dict[str, Dict[str, Any]] = {}


# ─────────────────────────────────────────────
# AGENT CARD
# The A2A spec requires agents to expose their capabilities.
# Clients read this to understand what tasks this agent accepts.
# ─────────────────────────────────────────────
@app.get("/agent-card")
async def agent_card():
    return {
        "name": "Allocation Agent",
        "version": "1.0.0",
        "description": "Computes optimal inventory allocation plans based on current stock levels",
        "capabilities": ["inventory_allocation", "stock_balancing"],
        "input_schema": {
            "product_id": "optional string — filter to specific product",
            "region": "optional string — target region for allocation",
            "role": "string — caller role (analyst|admin)"
        },
        "output_schema": {
            "allocation_plan": "list of transfer recommendations",
            "summary": "human-readable summary",
            "total_units_transferred": "integer"
        }
    }


# ─────────────────────────────────────────────
# TASK INPUT MODEL
# ─────────────────────────────────────────────
class AllocationTaskInput(BaseModel):
    task_id: str
    type: str
    product_id: str | None = None
    region: str | None = None
    role: str = "analyst"
    requested_at: str = ""


# ─────────────────────────────────────────────
# POST /tasks — Create a new allocation task
# ─────────────────────────────────────────────
@app.post("/tasks")
async def create_task(task_input: AllocationTaskInput, background_tasks: BackgroundTasks):
    """
    Accept a new allocation task and begin processing it asynchronously.

    The task starts immediately in the background.
    The caller gets back the task_id and polls GET /tasks/{id} for status.
    """
    task_id = task_input.task_id or str(uuid.uuid4())

    # Initialize task state
    tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "input": task_input.dict(),
        "result": None,
        "error": None
    }

    # Kick off the allocation computation in the background
    # FastAPI's BackgroundTasks runs this after the response is sent
    background_tasks.add_task(
        compute_allocation,
        task_id=task_id,
        product_id=task_input.product_id,
        region=task_input.region
    )

    logger.info(f"Created allocation task: {task_id}")
    return {"task_id": task_id, "status": "pending"}


# ─────────────────────────────────────────────
# GET /tasks/{task_id} — Poll task status
# ─────────────────────────────────────────────
@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return tasks[task_id]


# ─────────────────────────────────────────────
# ALLOCATION COMPUTATION
#
# This is the actual business logic.
# Simple algorithm:
#   1. For each deficit location (stock < reorder_point):
#      find a surplus location (stock > reorder_point * 1.5)
#      and transfer enough units to bring deficit to reorder_point
#   2. Return the transfer plan
# ─────────────────────────────────────────────
async def compute_allocation(task_id: str, product_id: str | None, region: str | None):
    """Background task: compute the allocation plan and update task state."""
    tasks[task_id]["status"] = "in_progress"
    logger.info(f"Computing allocation for task {task_id}")

    try:
        # Simulate some processing time (replace with real computation)
        await asyncio.sleep(2)

        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
        async with pool.acquire() as conn:
            # Get inventory for all products (or specific product)
            conditions = []
            params = []
            if product_id:
                conditions.append(f"i.product_id = ${len(params)+1}")
                params.append(product_id)

            where = "WHERE " + " AND ".join(conditions) if conditions else ""

            rows = await conn.fetch(f"""
                SELECT
                    i.product_id, p.product_name, i.location,
                    i.stock_level, i.reorder_point, i.max_capacity,
                    i.stock_level - i.reorder_point AS buffer
                FROM inventory i
                JOIN products p ON i.product_id = p.product_id
                {where}
                ORDER BY i.product_id, buffer ASC
            """, *params)

        await pool.close()

        inventory = [dict(r) for r in rows]

        # Identify deficits and surpluses
        deficits = [i for i in inventory if i["buffer"] < 0]
        surpluses = [i for i in inventory if i["buffer"] > i["reorder_point"] * 0.5]

        allocation_plan = []
        total_transferred = 0

        for deficit in deficits:
            # Find a surplus of the same product
            matching_surpluses = [
                s for s in surpluses
                if s["product_id"] == deficit["product_id"]
                and s["location"] != deficit["location"]
            ]
            if not matching_surpluses:
                continue

            surplus = matching_surpluses[0]   # take from the first available surplus
            units_needed = abs(deficit["buffer"])   # how many units to bring to reorder_point
            units_available = surplus["buffer"] // 2   # don't drain the surplus completely

            transfer_qty = min(units_needed, units_available)
            if transfer_qty <= 0:
                continue

            allocation_plan.append({
                "product_id": deficit["product_id"],
                "product_name": deficit["product_name"],
                "from_location": surplus["location"],
                "to_location": deficit["location"],
                "transfer_quantity": transfer_qty,
                "reason": f"Stock at {deficit['location']} is {abs(deficit['buffer'])} units below reorder point"
            })
            total_transferred += transfer_qty

        summary = (
            f"Allocation plan computed: {len(allocation_plan)} transfer(s), "
            f"{total_transferred} total units. "
            f"{len(deficits)} location(s) below reorder point identified."
        )

        tasks[task_id]["status"] = "completed"
        tasks[task_id]["result"] = {
            "allocation_plan": allocation_plan,
            "summary": summary,
            "total_units_transferred": total_transferred,
            "deficits_found": len(deficits),
            "completed_at": datetime.utcnow().isoformat()
        }
        logger.info(f"Allocation task {task_id} completed: {len(allocation_plan)} transfers")

    except Exception as e:
        logger.error(f"Allocation task {task_id} failed: {e}")
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = str(e)


# ─────────────────────────────────────────────
# POST /tasks/{task_id}/execute
#
# Day 6: Actually apply the allocation plan to the inventory table.
# Called by the supervisor hitl_node AFTER human approval.
#
# For each transfer in the plan:
#   - Subtract units from the surplus (from_location)
#   - Add units to the deficit (to_location)
#
# WHY not do this in compute_allocation?
# Separation of concerns: the compute step is read-only (safe to retry).
# The execute step is destructive (writes to DB) — it should only run
# once, after explicit human approval.
# ─────────────────────────────────────────────
class ExecuteDirectRequest(BaseModel):
    """
    Allows the supervisor to pass allocation transfers directly from graph state.
    Used when the in-memory task store has been cleared (e.g. after service restart).
    """
    allocation_plan: list[dict]


@app.post("/execute-direct")
async def execute_direct(req: ExecuteDirectRequest):
    """
    Execute allocation transfers passed directly in the request body.
    Called by the supervisor when the task_id is no longer in memory.
    """
    return await _apply_allocation_plan(req.allocation_plan)


@app.post("/tasks/{task_id}/execute")
async def execute_task(task_id: str):
    """
    Apply the allocation plan from a completed task to the inventory table.
    Only callable after the task is in 'completed' status.
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    task = tasks[task_id]
    if task["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Task {task_id} is not completed (status={task['status']})"
        )

    result = task.get("result", {})
    allocation_plan = result.get("allocation_plan", [])

    if not allocation_plan:
        return {"executed": 0, "message": "No transfers to apply."}

    result = await _apply_allocation_plan(allocation_plan)
    tasks[task_id]["status"] = "executed"
    tasks[task_id]["executed_at"] = datetime.utcnow().isoformat()
    return result


async def _apply_allocation_plan(allocation_plan: list) -> dict:
    """
    Core DB logic: apply inventory transfers for each item in the allocation plan.
    Shared by both /tasks/{id}/execute and /execute-direct.
    """
    if not allocation_plan:
        return {"executed": 0, "message": "No transfers to apply."}

    executed = 0
    errors = []

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        for transfer in allocation_plan:
            product_id = transfer["product_id"]
            from_loc = transfer["from_location"]
            to_loc = transfer["to_location"]
            qty = transfer["transfer_quantity"]

            try:
                async with conn.transaction():
                    # Deduct from surplus location
                    await conn.execute("""
                        UPDATE inventory
                        SET stock_level = stock_level - $1, last_updated = NOW()
                        WHERE product_id = $2 AND location = $3
                    """, qty, product_id, from_loc)

                    # Add to deficit location
                    await conn.execute("""
                        UPDATE inventory
                        SET stock_level = stock_level + $1, last_updated = NOW()
                        WHERE product_id = $2 AND location = $3
                    """, qty, product_id, to_loc)

                    executed += 1
                    logger.info(
                        f"Executed transfer: {qty} units of {product_id} "
                        f"{from_loc} → {to_loc}"
                    )
            except Exception as e:
                errors.append(f"{product_id} {from_loc}→{to_loc}: {str(e)}")
                logger.error(f"Transfer failed: {e}")
    finally:
        await conn.close()

    return {
        "executed": executed,
        "errors": errors,
        "message": f"Applied {executed} of {len(allocation_plan)} transfers to inventory."
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
