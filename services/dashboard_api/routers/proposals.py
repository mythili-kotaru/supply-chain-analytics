"""
Proposal routes (Day 4 — LangGraph HITL wired):
  GET  /proposals                  — list all (filterable by status)
  POST /proposals/{id}/approve     — resume LangGraph graph with approved=True
  POST /proposals/{id}/reject      — resume LangGraph graph with approved=False

Day 4 change in _update_proposal_status:
  Instead of just flipping the DB column, we now:
    1. Look up the proposal's thread_id
    2. POST to langgraph_agent /resume with {thread_id, approved, feedback}
    3. The graph unpauses, runs hitl_node, executes A2A if approved
    4. Update DB status based on the result

If the proposal has no thread_id (langgraph_agent was down when it was created),
we fall back gracefully — just flip the DB status column, same as Day 3.

Route signatures are IDENTICAL to Day 3. The frontend doesn't need to change.
"""
import json
import os
import logging
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
import asyncpg
import httpx
from auth import get_current_role

from database import get_db
from models import (
    Proposal, ProposalTrigger,
    ReplenishmentPayload, AllocationPayload, ForecastTuningPayload,
    ApproveRejectResponse,
)

logger = logging.getLogger(__name__)

# URL for the LangGraph agent service — set in docker-compose env
LANGGRAPH_AGENT_URL = os.getenv("LANGGRAPH_AGENT_URL", "http://localhost:8004")

# UUID v4 pattern for proposal ID validation
_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_jsonb(value) -> dict | None:
    """asyncpg may return JSONB as a string or dict depending on version."""
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)


def _row_to_proposal(row: asyncpg.Record) -> Proposal:
    """
    Convert a raw asyncpg row from the proposals table into a typed Proposal.
    JSONB columns come back as dicts; we validate them into nested models.
    """
    trigger = ProposalTrigger(
        product_id=row["trigger_product_id"],
        product_name=row["trigger_product_name"],
        location=row["trigger_location"],
        metric=row["trigger_metric"],
        current_value=float(row["trigger_current_value"]),
        threshold=float(row["trigger_threshold"]),
    )

    replenishment = None
    rp = _parse_jsonb(row["replenishment_payload"])
    if rp:
        replenishment = ReplenishmentPayload(**rp)

    allocation = None
    ap = _parse_jsonb(row["allocation_payload"])
    if ap:
        allocation = AllocationPayload(**ap)

    forecast_tuning = None
    fp = _parse_jsonb(row["forecast_tuning_payload"])
    if fp:
        forecast_tuning = ForecastTuningPayload(**fp)

    return Proposal(
        id=row["id"],
        type=row["type"],
        status=row["status"],
        severity=row["severity"],
        created_at=row["created_at"].isoformat(),
        trigger=trigger,
        agent_reasoning=row["agent_reasoning"],
        latency_ms=row["latency_ms"],
        nodes_visited=list(row["nodes_visited"]) if row["nodes_visited"] else None,
        thread_id=row["thread_id"],
        trace_id=row["trace_id"] if "trace_id" in row.keys() else None,
        trace_url=row["trace_url"] if "trace_url" in row.keys() else None,
        replenishment=replenishment,
        allocation=allocation,
        forecast_tuning=forecast_tuning,
    )


async def _resume_langgraph(
    proposal_id: str,
    thread_id: str,
    approved: bool,
    feedback: str = "",
    user_role: str = "admin",
) -> dict:
    """
    Call POST /resume on the LangGraph agent service.

    This unpauses the checkpointed graph, which then:
      - Runs hitl_node with human_response={approved, feedback}
      - If approved: executes A2A allocation/replenishment/recommendation
      - Reaches END node

    Returns the ResumeResponse dict from the agent service.

    WHY a separate HTTP call and not importing the graph directly?
    The dashboard_api service doesn't have access to the agents/ package
    or the OpenAI key. Keeping LangGraph in its own service maintains
    clean separation. The dashboard API is purely a CRUD + scheduling layer.
    """
    payload = {
        "proposal_id": proposal_id,
        "thread_id": thread_id,
        "approved": approved,
        "feedback": feedback,
        "user_role": user_role,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{LANGGRAPH_AGENT_URL}/resume", json=payload)
        resp.raise_for_status()
        return resp.json()


async def _update_proposal_status(
    db: asyncpg.Pool,
    proposal_id: str,
    new_status: str,
    feedback: str = "",
    user_role: str = "analyst",
) -> dict:
    """
    Day 4: Resume the LangGraph graph (if thread_id exists), then update DB.

    Flow:
      1. Fetch proposal row — check it exists and is still pending
      2. If thread_id is set → call /resume on langgraph_agent
         The graph runs to completion (may trigger A2A allocation/replenishment)
         The /resume call updates the DB status itself (inside the agent service)
      3. If no thread_id → fall back to direct DB update (langgraph_agent was down)

    Returns a dict with metadata about what happened (used in the HTTP response).
    """
    row = await db.fetchrow(
        "SELECT id, status, thread_id, type FROM proposals WHERE id = $1",
        proposal_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")
    if row["status"] != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Proposal {proposal_id} is already {row['status']} — cannot change again",
        )

    approved = (new_status == "approved")
    thread_id = row["thread_id"]

    if thread_id:
        # ── Path A: LangGraph is wired — resume the graph ────────────────────
        # The agent service handles the DB update internally (in run_resume).
        logger.info(
            f"Resuming LangGraph graph for proposal {proposal_id} "
            f"(thread_id={thread_id}, approved={approved})"
        )
        try:
            result = await _resume_langgraph(
                proposal_id=proposal_id,
                thread_id=thread_id,
                approved=approved,
                feedback=feedback,
                user_role=user_role,
            )
            logger.info(
                f"Graph completed for proposal {proposal_id}: "
                f"status={result.get('status')} nodes={result.get('nodes_visited')}"
            )
            return {
                "via_langgraph": True,
                "graph_status": result.get("status"),
                "final_message": result.get("final_message", ""),
                "nodes_visited": result.get("nodes_visited", []),
            }
        except httpx.ConnectError:
            logger.warning(
                f"langgraph_agent unreachable — falling back to direct DB update "
                f"for proposal {proposal_id}"
            )
            # Fall through to Path B
        except httpx.HTTPStatusError as e:
            logger.error(
                f"langgraph_agent /resume returned {e.response.status_code}: {e.response.text}"
            )
            # Fall through to Path B

    # ── Path B: No thread_id or service down — direct DB update ──────────────
    logger.info(f"Direct DB update for proposal {proposal_id} → {new_status}")
    await db.execute(
        "UPDATE proposals SET status = $1 WHERE id = $2",
        new_status, proposal_id,
    )
    return {
        "via_langgraph": False,
        "graph_status": None,
        "final_message": f"Status updated to {new_status} (no LangGraph thread).",
        "nodes_visited": [],
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/proposals", response_model=list[Proposal])
async def get_proposals(
    status: Optional[str] = Query(None, description="Filter by status: pending | approved | rejected"),
    db: asyncpg.Pool = Depends(get_db),
):
    """
    Returns proposals ordered by: pending first (most actionable),
    then by severity (CRITICAL > HIGH > MEDIUM), then newest first.
    """
    if status and status not in ("pending", "approved", "rejected"):
        raise HTTPException(status_code=400, detail="status must be pending, approved, or rejected")

    query = """
        SELECT *
        FROM proposals
        {}
        ORDER BY
            CASE status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1 ELSE 2 END,
            CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 ELSE 2 END,
            created_at DESC
    """.format("WHERE status = $1" if status else "")

    rows = await (
        db.fetch(query, status) if status else db.fetch(query)
    )

    return [_row_to_proposal(r) for r in rows]


@router.post("/proposals/{proposal_id}/approve", response_model=ApproveRejectResponse)
async def approve_proposal(
    proposal_id: str,
    db: asyncpg.Pool = Depends(get_db),
    role: str = Depends(get_current_role),
):
    """
    Approve a pending proposal.

    Day 4: If the proposal has a LangGraph thread_id, this resumes the
    paused graph which then executes the actual A2A action (allocation
    transfer or replenishment PO). May take up to 30s if A2A agents
    are doing real work.

    If no thread_id (agent service was down), falls back to DB-only update.
    """
    if role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied: Only administrator role can approve proposals.")
    if not _UUID_RE.match(proposal_id):
        raise HTTPException(status_code=400, detail="Invalid proposal ID format (expected UUID)")
    result = await _update_proposal_status(db, proposal_id, "approved", user_role=role)

    if result["via_langgraph"]:
        message = (
            f"LangGraph resumed — action executed. "
            f"Nodes: {' → '.join(result['nodes_visited'])}. "
            f"{result['final_message']}"
        )
    else:
        message = "Proposal approved. (LangGraph not available — status updated directly.)"

    return ApproveRejectResponse(
        id=proposal_id,
        status="approved",
        message=message,
    )


@router.post("/proposals/{proposal_id}/reject", response_model=ApproveRejectResponse)
async def reject_proposal(
    proposal_id: str,
    db: asyncpg.Pool = Depends(get_db),
    role: str = Depends(get_current_role),
):
    """
    Reject a pending proposal.
    Resumes the paused LangGraph graph with approved=False, which records
    the rejection in the graph state and terminates cleanly.
    """
    if role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied: Only administrator role can reject proposals.")
    if not _UUID_RE.match(proposal_id):
        raise HTTPException(status_code=400, detail="Invalid proposal ID format (expected UUID)")
    result = await _update_proposal_status(db, proposal_id, "rejected", feedback="Rejected by ops manager", user_role=role)

    if result["via_langgraph"]:
        message = f"Proposal rejected. LangGraph graph terminated cleanly."
    else:
        message = "Proposal rejected."

    return ApproveRejectResponse(
        id=proposal_id,
        status="rejected",
        message=message,
    )
