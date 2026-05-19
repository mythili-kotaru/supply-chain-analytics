"""
Proposal routes:
  GET  /proposals                  — list all (filterable by status)
  POST /proposals/{id}/approve     — mark approved
  POST /proposals/{id}/reject      — mark rejected

Design note on approve/reject:
Today these just flip the DB status column. On Day 4 we'll replace the
body of _update_proposal_status with a call to LangGraph's resume API
(POST to the supervisor's /resume endpoint with the thread_id), which
will unpause the graph checkpoint and trigger actual A2A execution.
The route signature stays identical — only the internal logic changes.

This is why we store thread_id on each proposal row right now — we're
planting the hook for Day 4.
"""
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
import asyncpg

from database import get_db
from models import (
    Proposal, ProposalTrigger,
    ReplenishmentPayload, AllocationPayload, ForecastTuningPayload,
    ApproveRejectResponse,
)

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
        replenishment=replenishment,
        allocation=allocation,
        forecast_tuning=forecast_tuning,
    )


async def _update_proposal_status(
    db: asyncpg.Pool,
    proposal_id: str,
    new_status: str,
) -> asyncpg.Record:
    """
    Flip the proposal status.

    Day 4 TODO: before updating status, check if the proposal has a
    thread_id. If it does, POST to the LangGraph supervisor's /resume
    endpoint to unpause the graph:
        await resume_langgraph(thread_id=row['thread_id'], approved=(new_status == 'approved'))
    Then update the DB status.
    """
    row = await db.fetchrow(
        "SELECT id, status, thread_id FROM proposals WHERE id = $1",
        proposal_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id} not found")
    if row["status"] != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Proposal {proposal_id} is already {row['status']} — cannot change again",
        )

    await db.execute(
        "UPDATE proposals SET status = $1 WHERE id = $2",
        new_status, proposal_id,
    )
    return row


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
):
    await _update_proposal_status(db, proposal_id, "approved")
    return ApproveRejectResponse(
        id=proposal_id,
        status="approved",
        message="Proposal approved. Execution queued.",
        # Day 4: message will say "LangGraph resumed — A2A task dispatched."
    )


@router.post("/proposals/{proposal_id}/reject", response_model=ApproveRejectResponse)
async def reject_proposal(
    proposal_id: str,
    db: asyncpg.Pool = Depends(get_db),
):
    await _update_proposal_status(db, proposal_id, "rejected")
    return ApproveRejectResponse(
        id=proposal_id,
        status="rejected",
        message="Proposal rejected.",
    )
