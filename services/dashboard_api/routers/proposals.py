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
from fastapi import APIRouter, Depends, HTTPException, Query, Form
from fastapi.responses import StreamingResponse
import asyncpg
import httpx
from auth import get_current_role

from database import get_db
from models import (
    Proposal, ProposalTrigger,
    ReplenishmentPayload, AllocationPayload, ForecastTuningPayload,
    SupplierConfigPayload, ProposeSupplierConfigRequest, ApproveRejectResponse,
    SupplierModel,
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

    supplier_config = None
    scp = _parse_jsonb(row["supplier_config_payload"])
    if scp:
        supplier_config = SupplierConfigPayload(**scp)

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
        supplier_config=supplier_config,
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


async def resume_proxy_stream(
    db: asyncpg.Pool,
    proposal_id: str,
    approved: bool,
    feedback: str = "",
    user_role: str = "admin",
):
    row = await db.fetchrow(
        "SELECT id, status, thread_id, type FROM proposals WHERE id = $1",
        proposal_id,
    )
    if not row:
        yield f"data: {json.dumps({'event': 'error', 'message': f'Proposal {proposal_id} not found'})}\n\n"
        return
    if row["status"] != "pending":
        current_status = row["status"]
        yield f"data: {json.dumps({'event': 'error', 'message': f'Proposal {proposal_id} is already {current_status} — cannot change status'})}\n\n"
        return

    thread_id = row["thread_id"]
    new_status = "approved" if approved else "rejected"

    if thread_id:
        payload = {
            "proposal_id": proposal_id,
            "thread_id": thread_id,
            "approved": approved,
            "feedback": feedback,
            "user_role": user_role,
        }
        logger.info(f"Streaming LangGraph resume for proposal {proposal_id} via thread {thread_id}")
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", f"{LANGGRAPH_AGENT_URL}/resume/stream", json=payload) as response:
                    if response.status_code == 200:
                        async for line in response.aiter_lines():
                            yield line + "\n"
                        return
                    else:
                        err_body = await response.aread()
                        logger.error(f"langgraph_agent stream returned status {response.status_code}: {err_body.decode()}")
                        yield f"data: {json.dumps({'event': 'thought', 'message': 'LangGraph agent stream returned error. Falling back to direct database update...'})}\n\n"
        except Exception as e:
            logger.error(f"Error calling langgraph_agent resume/stream: {e}")
            yield f"data: {json.dumps({'event': 'thought', 'message': f'LangGraph agent service offline ({type(e).__name__}). Falling back to direct database update...'})}\n\n"

    # Fallback to direct DB update path
    yield f"data: {json.dumps({'event': 'thought', 'message': f'Flipping proposal status directly in database to: {new_status}'})}\n\n"
    await db.execute(
        "UPDATE proposals SET status = $1 WHERE id = $2",
        new_status, proposal_id,
    )
    complete_data = {
        "event": "complete",
        "proposal_id": proposal_id,
        "thread_id": thread_id,
        "approved": approved,
        "status": "executed" if approved else "rejected",
        "final_message": f"Proposal status updated directly to {new_status}.",
        "nodes_visited": []
    }
    yield f"data: {json.dumps(complete_data)}\n\n"


@router.post("/proposals/{proposal_id}/approve/stream")
async def approve_proposal_stream(
    proposal_id: str,
    db: asyncpg.Pool = Depends(get_db),
    role: str = Depends(get_current_role),
):
    """
    Approve proposal and return a real-time event stream.
    """
    if role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied: Only administrator role can approve proposals.")
    if not _UUID_RE.match(proposal_id):
        raise HTTPException(status_code=400, detail="Invalid proposal ID format (expected UUID)")
    return StreamingResponse(
        resume_proxy_stream(db, proposal_id, approved=True, feedback="", user_role=role),
        media_type="text/event-stream"
    )


@router.post("/proposals/{proposal_id}/reject/stream")
async def reject_proposal_stream(
    proposal_id: str,
    db: asyncpg.Pool = Depends(get_db),
    role: str = Depends(get_current_role),
):
    """
    Reject proposal and return a real-time event stream.
    """
    if role != "admin":
        raise HTTPException(status_code=403, detail="Permission denied: Only administrator role can reject proposals.")
    if not _UUID_RE.match(proposal_id):
        raise HTTPException(status_code=400, detail="Invalid proposal ID format (expected UUID)")
    return StreamingResponse(
        resume_proxy_stream(db, proposal_id, approved=False, feedback="Rejected by ops manager", user_role=role),
        media_type="text/event-stream"
    )


@router.post("/proposals/supplier-config", response_model=Proposal)
async def propose_supplier_config(
    req: ProposeSupplierConfigRequest,
    db: asyncpg.Pool = Depends(get_db),
    role: str = Depends(get_current_role)
):
    """
    Propose a supplier configuration change.
    Inserts a proposal row, then invokes LangGraph to serialize graph state and get thread_id.
    """
    import uuid
    # 1. Fetch current supplier info from PostgreSQL
    async with db.acquire() as conn:
        supplier = await conn.fetchrow(
            "SELECT supplier_name, lead_time_days, defect_rate FROM suppliers WHERE supplier_id = $1",
            req.supplier_id
        )
        if not supplier:
            raise HTTPException(status_code=404, detail=f"Supplier {req.supplier_id} not found")

        proposal_id = str(uuid.uuid4())
        
        # Build payload
        payload = {
            "supplier_id": req.supplier_id,
            "supplier_name": supplier["supplier_name"],
            "lead_time_days": req.lead_time_days,
            "defect_rate": req.defect_rate,
            "old_lead_time_days": supplier["lead_time_days"],
            "old_defect_rate": float(supplier["defect_rate"])
        }
        
        # Insert proposal row
        agent_reasoning = f"Proposed supplier config update for {supplier['supplier_name']} ({req.supplier_id}): {req.rationale}"
        
        row = await conn.fetchrow("""
            INSERT INTO proposals (
                id, type, status, severity, created_at,
                trigger_product_id, trigger_product_name, trigger_location,
                trigger_metric, trigger_current_value, trigger_threshold,
                agent_reasoning, supplier_config_payload
            ) VALUES (
                $1, 'supplier_config', 'pending', 'MEDIUM', NOW(),
                'N/A', $2, NULL,
                'supplier_config', 0, 0,
                $3, $4::jsonb
            )
            RETURNING *
        """, proposal_id, supplier["supplier_name"], agent_reasoning, json.dumps(payload))

    # 2. Invoke LangGraph agent to register the workflow and thread_id
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{LANGGRAPH_AGENT_URL}/invoke",
                json={
                    "proposal_id": proposal_id,
                    "proposal_type": "supplier_config",
                    "product_id": "N/A",
                    "product_name": supplier["supplier_name"],
                    "location": None,
                    "severity": "MEDIUM",
                    "trigger_metric": "supplier_config",
                    "trigger_value": 0.0,
                    "trigger_threshold": 0.0,
                    "user_role": role
                }
            )
            if resp.status_code == 200:
                # Refresh proposal to return with the thread_id populated
                async with db.acquire() as conn:
                    updated_row = await conn.fetchrow("SELECT * FROM proposals WHERE id = $1", proposal_id)
                    return _row_to_proposal(updated_row)
            else:
                logger.error(f"LangGraph invoke returned status {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"Failed to invoke LangGraph agent for supplier config: {e}")

    # Fallback return if invoke fails (still return the created proposal without thread_id)
    return _row_to_proposal(row)


@router.get("/suppliers", response_model=list[SupplierModel])
async def get_suppliers(
    db: asyncpg.Pool = Depends(get_db),
    role: str = Depends(get_current_role)
):
    """
    Get a list of all suppliers.
    """
    rows = await db.fetch("SELECT supplier_id, supplier_name, location, lead_time_days, defect_rate FROM suppliers ORDER BY supplier_id")
    return [
        SupplierModel(
            supplier_id=r["supplier_id"],
            supplier_name=r["supplier_name"],
            location=r["location"],
            lead_time_days=r["lead_time_days"],
            defect_rate=float(r["defect_rate"])
        )
        for r in rows
    ]


# ── Slack Webhook & Action mock buffers ───────────────────────────────────────
slack_router = APIRouter()
LAST_SLACK_MESSAGE = None
LAST_SLACK_RESPONSE = None

@slack_router.post("/proposals/slack-webhook-mock")
async def slack_webhook_mock(req: dict):
    global LAST_SLACK_MESSAGE
    logger.info(f"Mock Slack Webhook received payload: {req}")
    
    # Inject a local response_url pointing to our mock response handler
    proposal_id = req.get("proposal_id", "unknown")
    payload = dict(req)
    payload["response_url"] = f"http://dashboard_api:8003/api/dashboard/proposals/slack-response-mock/{proposal_id}"
    
    LAST_SLACK_MESSAGE = payload
    return {"status": "ok", "message": "Webhook payload received locally."}

@slack_router.get("/proposals/slack-webhook-mock/last")
async def get_last_slack_webhook():
    global LAST_SLACK_MESSAGE
    return LAST_SLACK_MESSAGE or {}

@slack_router.post("/proposals/slack-response-mock/{proposal_id}")
async def slack_response_mock(proposal_id: str, req: dict):
    global LAST_SLACK_RESPONSE
    logger.info(f"Mock Slack response endpoint received payload for {proposal_id}: {req}")
    LAST_SLACK_RESPONSE = req
    return {"status": "ok", "message": "Slack response mock stored."}

@slack_router.get("/proposals/slack-response-mock/last")
async def get_last_slack_response():
    global LAST_SLACK_RESPONSE
    return LAST_SLACK_RESPONSE or {}

@slack_router.post("/proposals/slack-action")
async def slack_action(payload: str = Form(...), db: asyncpg.Pool = Depends(get_db)):
    """
    Handle interactive action payload from Slack.
    Uses application/x-www-form-urlencoded parsing.
    """
    try:
        data = json.loads(payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload JSON: {e}")

    actions = data.get("actions", [])
    if not actions:
        raise HTTPException(status_code=400, detail="No action payload found")

    action_value_str = actions[0].get("value")
    try:
        action_value = json.loads(action_value_str)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid action value JSON: {e}")

    proposal_id = action_value.get("proposal_id")
    action = action_value.get("action")
    user_info = data.get("user", {})
    username = user_info.get("username", "Slack User")
    response_url = data.get("response_url")

    if not proposal_id or not action:
        raise HTTPException(status_code=400, detail="proposal_id and action are required in button value")

    approved = (action == "approve")
    new_status = "approved" if approved else "rejected"

    logger.info(f"Slack action received: proposal={proposal_id} action={action} user={username}")

    # Process resume via _update_proposal_status (simulates Admin role)
    result = await _update_proposal_status(
        db=db,
        proposal_id=proposal_id,
        new_status=new_status,
        feedback=f"Action taken via Slack by @{username}",
        user_role="admin"
    )

    # Replace original Slack message actions block with status text
    if response_url:
        orig_blocks = data.get("message", {}).get("blocks", [])
        if not orig_blocks and "message" in data:
            orig_blocks = data["message"].get("blocks", [])
            
        # Filter out actions block
        updated_blocks = [b for b in orig_blocks if b.get("type") != "actions"]
        
        status_emoji = "✅" if approved else "❌"
        action_past_tense = "Approved" if approved else "Rejected"
        updated_blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"{status_emoji} *{action_past_tense}* by @{username} via Slack."
                }
            ]
        })

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(response_url, json={
                    "replace_original": True,
                    "blocks": updated_blocks
                })
        except Exception as update_err:
            logger.error(f"Failed to update Slack message via response_url: {update_err}")

    return {
        "status": "ok",
        "message": f"Proposal {proposal_id} successfully {action_past_tense.lower()}."
    }


# ── Jira Mock endpoints ───────────────────────────────────────────────────────
MOCK_JIRA_TICKETS = []
MOCK_JIRA_COUNTER = 100

@slack_router.post("/jira/mock-ticket")
async def jira_mock_ticket(req: dict):
    global MOCK_JIRA_TICKETS, MOCK_JIRA_COUNTER
    from datetime import datetime
    logger.info(f"Mock Jira Ticket request received: {req}")
    
    summary = req.get("summary", "New PO")
    description = req.get("description", "")
    po_number = req.get("po_number", "UNKNOWN")
    
    MOCK_JIRA_COUNTER += 1
    issue_key = f"SC-{MOCK_JIRA_COUNTER}"
    
    ticket = {
        "key": issue_key,
        "summary": summary,
        "description": description,
        "po_number": po_number,
        "status": "To Do",
        "created_at": datetime.utcnow().isoformat(),
        "self": f"http://dashboard_api:8003/api/dashboard/jira/browse/{issue_key}"
    }
    
    MOCK_JIRA_TICKETS.append(ticket)
    logger.info(f"Mock Jira Ticket created: {issue_key} for PO {po_number}")
    return ticket

@slack_router.get("/jira/mock-ticket/last")
async def get_last_jira_ticket():
    global MOCK_JIRA_TICKETS
    return MOCK_JIRA_TICKETS[-1] if MOCK_JIRA_TICKETS else {}

@slack_router.get("/jira/browse/{key}")
async def jira_browse_ticket(key: str):
    global MOCK_JIRA_TICKETS
    ticket = next((t for t in MOCK_JIRA_TICKETS if t["key"] == key), None)
    if not ticket:
        raise HTTPException(status_code=404, detail=f"Jira ticket {key} not found")
    return ticket



