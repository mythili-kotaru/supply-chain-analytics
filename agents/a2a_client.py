"""
agents/a2a_client.py
──────────────────────
Client for communicating with A2A (Agent-to-Agent) FastAPI services.

WHAT IS A2A?
A2A is a protocol for agents to delegate tasks to other agents.
It's similar to REST but specifically designed for AI agent workflows.

KEY CONCEPTS:
  - Task: a unit of work with a lifecycle (pending → in_progress → completed/failed)
  - Agent Card: metadata about what an agent can do (like an API spec)
  - Polling: since tasks are async, the client polls until done

WHY POLLING and not webhooks?
  - Webhooks require the caller to expose a public endpoint (harder in local dev)
  - Polling is simpler to implement and debug
  - The A2A spec supports both — polling is the standard for internal services

THE TASK LIFECYCLE:
  1. Client calls POST /tasks (trigger) → gets task_id
  2. Agent starts work asynchronously
  3. Client calls GET /tasks/{task_id} repeatedly (polling)
  4. When status == 'completed', client reads the result
  5. If status == 'failed', client reads the error

In our implementation:
  - Supervisor calls trigger_allocation() → gets task_id
  - Supervisor calls poll_task() with exponential backoff
  - When done, reads allocation_result or replenishment_result
"""

import asyncio
import httpx
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

ALLOCATION_AGENT_URL = "http://localhost:8001"    # or allocation_agent:8001 inside Docker
REPLENISHMENT_AGENT_URL = "http://localhost:8002"

MAX_POLL_ATTEMPTS = 20
POLL_INTERVAL_SECONDS = 2


async def trigger_allocation(
    product_id: str | None,
    region: str | None,
    role: str
) -> str:
    """
    Send an allocation task to the Allocation Agent.
    Returns the task_id for polling.
    """
    task_id = str(uuid.uuid4())
    payload = {
        "task_id": task_id,
        "type": "allocation",
        "product_id": product_id,
        "region": region,
        "requested_at": datetime.utcnow().isoformat(),
        "role": role
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(f"{ALLOCATION_AGENT_URL}/tasks", json=payload)
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Allocation task created: {data.get('task_id')}")
            return data.get("task_id", task_id)
        except httpx.RequestError as e:
            logger.error(f"Failed to reach allocation agent: {e}")
            raise


async def trigger_replenishment(
    product_id: str | None,
    role: str
) -> str:
    """
    Send a replenishment task to the Replenishment Agent.
    Returns the task_id for polling.
    """
    task_id = str(uuid.uuid4())
    payload = {
        "task_id": task_id,
        "type": "replenishment",
        "product_id": product_id,
        "requested_at": datetime.utcnow().isoformat(),
        "role": role
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(f"{REPLENISHMENT_AGENT_URL}/tasks", json=payload)
            resp.raise_for_status()
            return resp.json().get("task_id", task_id)
        except httpx.RequestError as e:
            logger.error(f"Failed to reach replenishment agent: {e}")
            raise


async def poll_task(agent_type: str, task_id: str) -> dict | None:
    """
    Poll an A2A agent until the task completes or fails.

    Uses linear backoff (POLL_INTERVAL_SECONDS between each attempt).
    In production: use exponential backoff with jitter to avoid thundering herd.

    Args:
        agent_type: 'allocation' or 'replenishment'
        task_id: The task UUID returned by trigger_*

    Returns:
        The result dict from the agent, or None if failed/timed out.
    """
    if not task_id:
        return None

    base_url = ALLOCATION_AGENT_URL if agent_type == "allocation" else REPLENISHMENT_AGENT_URL

    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(MAX_POLL_ATTEMPTS):
            try:
                resp = await client.get(f"{base_url}/tasks/{task_id}")
                resp.raise_for_status()
                data = resp.json()
                status = data.get("status")

                logger.info(f"Poll {agent_type} task {task_id}: status={status} (attempt {attempt+1})")

                if status == "completed":
                    return data.get("result")
                elif status == "failed":
                    logger.error(f"Task {task_id} failed: {data.get('error')}")
                    return {"error": data.get("error"), "status": "failed"}
                # else: pending or in_progress — keep polling

            except httpx.RequestError as e:
                logger.warning(f"Poll attempt {attempt+1} failed: {e}")

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    logger.error(f"Task {task_id} timed out after {MAX_POLL_ATTEMPTS} attempts")
    return {"error": "Task timed out", "status": "timeout"}
