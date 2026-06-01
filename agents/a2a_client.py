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
import os
import random
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

# Read from env so this works both locally (localhost) and in Docker (service names).
# docker-compose sets ALLOCATION_AGENT_URL=http://allocation_agent:8001 on langgraph_agent.
ALLOCATION_AGENT_URL = os.getenv("ALLOCATION_AGENT_URL", "http://localhost:8001")
REPLENISHMENT_AGENT_URL = os.getenv("REPLENISHMENT_AGENT_URL", "http://localhost:8002")

MAX_POLL_ATTEMPTS = 20
POLL_BASE_INTERVAL = 1.5   # seconds — base for exponential backoff
POLL_MAX_INTERVAL = 10.0   # cap the backoff
TRIGGER_MAX_RETRIES = 3    # retries for trigger HTTP calls


# ─────────────────────────────────────────────
# RETRY HELPER
#
# Wraps an async HTTP call with exponential backoff + jitter.
# Used for trigger_* functions where a single transient failure
# (e.g., service restarting) shouldn't fail the whole proposal.
# ─────────────────────────────────────────────
async def _retry_post(client: httpx.AsyncClient, url: str, payload: dict) -> httpx.Response:
    """POST with exponential backoff retry on transient errors."""
    for attempt in range(TRIGGER_MAX_RETRIES):
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            if attempt == TRIGGER_MAX_RETRIES - 1:
                logger.error(f"All {TRIGGER_MAX_RETRIES} retries exhausted for {url}: {e}")
                raise
            wait = (2 ** attempt) + random.uniform(0, 0.5)
            logger.warning(f"Retry {attempt+1}/{TRIGGER_MAX_RETRIES} for {url} in {wait:.1f}s: {e}")
            await asyncio.sleep(wait)
        except httpx.HTTPStatusError:
            raise  # don't retry 4xx/5xx — those are application-level errors
    raise RuntimeError("Unreachable")  # satisfies type checker


async def trigger_allocation(
    product_id: str | None,
    region: str | None,
    role: str
) -> str:
    """
    Send an allocation task to the Allocation Agent.
    Retries up to 3 times on transient connection errors.
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
        resp = await _retry_post(client, f"{ALLOCATION_AGENT_URL}/tasks", payload)
        data = resp.json()
        logger.info(f"Allocation task created: {data.get('task_id')}")
        return data.get("task_id", task_id)


async def trigger_replenishment(
    product_id: str | None,
    role: str
) -> str:
    """
    Send a replenishment task to the Replenishment Agent.
    Retries up to 3 times on transient connection errors.
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
        resp = await _retry_post(client, f"{REPLENISHMENT_AGENT_URL}/tasks", payload)
        return resp.json().get("task_id", task_id)


async def poll_task(agent_type: str, task_id: str) -> dict | None:
    """
    Poll an A2A agent until the task completes or fails.

    Uses exponential backoff with jitter to avoid thundering herd.
    Starts at 1.5s, doubles each attempt, caps at 10s.

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

            # Exponential backoff with jitter: 1.5, 3, 6, 10, 10, ...
            wait = min(POLL_BASE_INTERVAL * (2 ** attempt), POLL_MAX_INTERVAL)
            wait += random.uniform(0, 0.5)
            await asyncio.sleep(wait)

    logger.error(f"Task {task_id} timed out after {MAX_POLL_ATTEMPTS} attempts")
    return {"error": "Task timed out", "status": "timeout"}
