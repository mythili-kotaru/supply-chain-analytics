"""
services/langgraph_agent/main.py
──────────────────────────────────
FastAPI wrapper around the LangGraph supervisor graph.

WHY a separate service and not calling LangGraph directly inside the dashboard API?
  1. Isolation: the dashboard API is already doing a lot (APScheduler, DB queries,
     routing). Adding LangGraph (OpenAI calls, A2A polling) would bloat it.
  2. Independent scaling: LangGraph runs are CPU/IO heavy. You can scale this
     service independently from the dashboard API.
  3. Clean boundaries: the dashboard API knows nothing about LangGraph internals.
     It just calls POST /invoke → gets thread_id, POST /resume → gets result.

TWO KEY ENDPOINTS:

  POST /invoke
  ────────────
  Called by the monitor when a proposal is first created.
  Starts the supervisor graph with the proposal context.
  The graph runs: supervisor → (sql/forecasting/allocation_replenishment) → HITL
  At HITL, LangGraph hits interrupt_before=["hitl"] and PAUSES.
  The graph state is checkpointed to SQLite. thread_id is returned.
  The graph stays paused until /resume is called.

  POST /resume
  ────────────
  Called when the ops manager clicks Approve or Reject on the dashboard.
  Sends Command(resume={approved, feedback}) to the checkpointed graph.
  The graph UNPAUSES: runs the hitl_node, then (if approved) executes
  the actual allocation/replenishment/recommendation action.
  Returns the final state.

CHECKPOINT STORE:
  SqliteSaver stores graph state in a local SQLite file.
  In production: PostgresSaver (asyncpg-based, multi-instance safe).
  The thread_id is the key — each proposal gets its own thread_id,
  so multiple proposals can be paused concurrently without conflict.

CONCEPT: LangGraph Command(resume=...)
  When a graph is paused at interrupt_before=["hitl"], the graph runner
  is waiting for a "resume" signal. You send it via:
    app.invoke(Command(resume=payload), config)
  where payload is the value that interrupt() returns to the node.
  The node then reads human_response = interrupt(approval_request)
  and human_response will be whatever we pass in Command(resume=...).
"""

import os
import uuid
import logging
import asyncio
from contextlib import asynccontextmanager
from typing import Any, Optional

import asyncpg
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# Command moved between LangGraph minor versions.
# Try the canonical location first, fall back to langgraph.types.
try:
    from langgraph.types import Command
except ImportError:
    from langgraph.pregel.types import Command  # type: ignore[no-redef]

# ── sys.path patch so agents/ is importable ──────────────────────────────────
# In Docker: agents/ is volume-mounted at /app/agents (same dir as main.py).
#            __file__ = /app/main.py  →  parent = /app  →  agents/ lives there.
# Locally:   run from repo root; agents/ is at repo_root/agents.
#            __file__ = .../services/langgraph_agent/main.py → parents[2] = repo root.
import sys, pathlib
_here = pathlib.Path(__file__).resolve().parent   # always /app in Docker
# Try /app first (Docker), then walk up to repo root (local dev)
for _candidate in [_here] + list(_here.parents):
    if (_candidate / "agents").is_dir():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        break

from agents.supervisor import build_supervisor_graph
from agents.state import SupplyChainState
from langchain_core.messages import HumanMessage, AIMessage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# LangSmith client — only initialized if LANGCHAIN_API_KEY is set.
# Used to look up the run URL after invoke so we can store it on the proposal.
_LANGSMITH_ENABLED = bool(os.getenv("LANGCHAIN_API_KEY"))
_langsmith_client = None
if _LANGSMITH_ENABLED:
    try:
        from langsmith import Client as LangSmithClient
        _langsmith_client = LangSmithClient()
        logger.info("LangSmith tracing enabled")
    except Exception as e:
        logger.warning(f"LangSmith client init failed: {e} — tracing disabled")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://scai:scai_password@localhost:5432/supply_chain")

# SQLite checkpoint DB path — persists across restarts
CHECKPOINT_DB = os.getenv("CHECKPOINT_DB", "/tmp/supply_chain_checkpoints.db")


# ── Pydantic models ───────────────────────────────────────────────────────────

class InvokeRequest(BaseModel):
    """
    Sent by monitor.py after creating a proposal.
    The agent needs enough context to generate a meaningful analysis.
    """
    proposal_id: str
    proposal_type: str          # 'replenishment' | 'allocation' | 'forecast_tuning'
    product_id: str
    product_name: str
    location: str | None = None
    severity: str = "HIGH"
    trigger_metric: str = "stock_level"
    trigger_value: float = 0.0
    trigger_threshold: float = 0.0
    user_role: str = "analyst"


class InvokeResponse(BaseModel):
    """Returned immediately after the graph pauses at HITL interrupt."""
    thread_id: str
    proposal_id: str
    status: str                 # always "paused_at_hitl" on success
    nodes_visited: list[str]
    agent_summary: str          # the AIMessage content before interrupt
    trace_id: Optional[str] = None    # LangSmith run UUID (None if tracing disabled)
    trace_url: Optional[str] = None   # Direct link to LangSmith run


class ResumeRequest(BaseModel):
    """
    Sent by the dashboard API when ops manager approves or rejects.
    """
    proposal_id: str
    thread_id: str
    approved: bool
    feedback: str = ""
    user_role: str = "admin"    # only admins can approve


class ResumeResponse(BaseModel):
    """Returned after the graph finishes post-approval execution."""
    proposal_id: str
    thread_id: str
    approved: bool
    status: str                 # 'executed' | 'rejected' | 'error'
    final_message: str
    nodes_visited: list[str]


# ── DB helper ─────────────────────────────────────────────────────────────────

async def update_proposal_thread_id(proposal_id: str, thread_id: str) -> None:
    """Store the LangGraph thread_id on the proposal row so /resume can find it."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "UPDATE proposals SET thread_id = $1 WHERE id = $2",
            thread_id, proposal_id
        )
        logger.info(f"Stored thread_id={thread_id} on proposal {proposal_id}")
    finally:
        await conn.close()


async def update_proposal_status(proposal_id: str, status: str) -> None:
    """Update proposal status after graph completes."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "UPDATE proposals SET status = $1 WHERE id = $2",
            status, proposal_id
        )
    finally:
        await conn.close()


async def update_proposal_replenishment_payload(proposal_id: str, replenishment_result: dict) -> None:
    """
    Write the replenishment agent's result back to replenishment_payload
    so the dashboard shows real PO data instead of the empty placeholder.
    """
    import json as _json
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "UPDATE proposals SET replenishment_payload = $1::jsonb WHERE id = $2",
            _json.dumps(replenishment_result),
            proposal_id
        )
        logger.info(f"Stored replenishment payload on proposal {proposal_id}")
    finally:
        await conn.close()


async def update_proposal_allocation_payload(proposal_id: str, allocation_result: dict) -> None:
    """
    Write the allocation agent's result back to allocation_payload
    so the dashboard shows real transfer data instead of null.
    """
    import json as _json
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "UPDATE proposals SET allocation_payload = $1::jsonb WHERE id = $2",
            _json.dumps(allocation_result),
            proposal_id
        )
        logger.info(f"Stored allocation payload on proposal {proposal_id}")
    finally:
        await conn.close()


async def update_proposal_forecast_payload(proposal_id: str, proposed_tuning: dict) -> None:
    """
    Write the forecasting agent's proposed_tuning back to forecast_tuning_payload
    so the dashboard can display the actual parameter changes for human review.
    """
    import json as _json
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            """UPDATE proposals
               SET forecast_tuning_payload = forecast_tuning_payload || $1::jsonb
               WHERE id = $2""",
            _json.dumps({
                "new_params":                proposed_tuning.get("new_params", {}),
                "old_params":                proposed_tuning.get("old_params", {}),
                "rationale":                 proposed_tuning.get("rationale", ""),
                "root_cause":                proposed_tuning.get("root_cause", ""),
                "expected_mape_improvement": proposed_tuning.get("expected_mape_improvement", ""),
            }),
            proposal_id
        )
        logger.info(f"Stored forecast tuning payload on proposal {proposal_id}")
    finally:
        await conn.close()


async def update_proposal_trace_id(proposal_id: str, trace_id: str, trace_url: Optional[str] = None) -> None:
    """Store the LangSmith run_id and URL on the proposal so the frontend can link to it."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "UPDATE proposals SET trace_id = $1, trace_url = $2 WHERE id = $3",
            trace_id, trace_url, proposal_id
        )
        logger.info(f"Stored trace_id={trace_id} trace_url={trace_url} on proposal {proposal_id}")
    finally:
        await conn.close()


def _get_langsmith_trace_url(run_name: str) -> tuple[Optional[str], Optional[str]]:
    """
    Find the most recent LangSmith run matching run_name and return (run_id, url).

    WHY search by run_name instead of run_id?
    LangGraph does NOT honour a run_id passed in the config — it generates its own
    internal run ID. So our pinned run_id is never registered in LangSmith and
    read_run(run_id) always fails with 404.

    Instead we search the project for runs with our run_name (which LangGraph DOES
    pass through) and take the most recent one. Since run_name includes both the
    proposal type and product name (e.g. "replenishment:Keratin Treatment Mask"),
    collisions are extremely unlikely.

    Returns (run_id, url) tuple — both None if not found.
    """
    if not _langsmith_client:
        return None, None
    try:
        project = os.getenv("LANGCHAIN_PROJECT", "supply-chain-ai")
        runs = list(_langsmith_client.list_runs(
            project_name=project,
            run_type="chain",
            filter=f'eq(name, "{run_name}")',
            limit=1,
        ))
        if runs:
            run = runs[0]
            run_id = str(run.id)
            url = getattr(run, "url", None)
            if not url:
                url = f"https://smith.langchain.com/runs/{run_id}"
            logger.info(f"Found LangSmith run: id={run_id} url={url}")
            return run_id, url
        else:
            logger.warning(f"No LangSmith run found for name='{run_name}'")
            return None, None
    except Exception as e:
        logger.warning(f"LangSmith run lookup failed for '{run_name}': {e}")
        return None, None


# ── Core graph runner ─────────────────────────────────────────────────────────

def _build_user_query(req: InvokeRequest) -> str:
    """
    Construct the natural language query that the supervisor will classify and route.
    This is what the supervisor_node sees as state['user_query'].
    """
    if req.proposal_type == "replenishment":
        return (
            f"Replenishment needed: {req.product_name} at {req.location} "
            f"has {req.trigger_value:.0f} units, below reorder point of "
            f"{req.trigger_threshold:.0f}. Severity: {req.severity}. "
            f"Analyze and prepare a replenishment recommendation."
        )
    elif req.proposal_type == "allocation":
        return (
            f"Allocation needed: {req.product_name} at {req.location} "
            f"is critically low ({req.trigger_value:.0f}/{req.trigger_threshold:.0f} units). "
            f"Check if surplus exists at another warehouse and propose a transfer."
        )
    elif req.proposal_type == "forecast_tuning":
        return (
            f"Forecast tuning needed: {req.product_name} model has MAPE of "
            f"{req.trigger_value:.1f}% (threshold: {req.trigger_threshold:.0f}%). "
            f"Analyze root cause and propose hyperparameter changes."
        )
    return f"Analyze supply chain issue for {req.product_name} (type: {req.proposal_type})"


async def run_invoke(req: InvokeRequest) -> InvokeResponse:
    """
    Start the supervisor graph for a proposal.
    The graph runs until it hits interrupt_before=["hitl"] and pauses.
    Returns the thread_id + a summary of what the agent found.

    WHY AsyncSqliteSaver?
    AsyncSqliteSaver uses aiosqlite under the hood — fully non-blocking.
    No thread executor needed. The checkpoint DB is written natively on
    the FastAPI event loop without stalling other requests.

    LANGSMITH RUN_NAME:
    Setting run_name in the config labels the top-level graph run in LangSmith.
    Format: "<proposal_type>:<product_name>" e.g. "replenishment:Keratin Treatment Mask"
    This makes runs easy to find in the LangSmith UI without reading the full trace.

    RUN_ID:
    We generate a deterministic run_id (uuid4) and pass it in the config.
    LangGraph uses it as the root run's ID, so we can look it up in LangSmith
    immediately after the graph pauses.
    """
    thread_id = str(uuid.uuid4())
    session_id = thread_id

    user_query = _build_user_query(req)

    initial_state: dict[str, Any] = {
        "user_query": user_query,
        "user_role": req.user_role,
        "session_id": session_id,
        "messages": [HumanMessage(content=user_query)],
        "human_approved": None,
        "tuning_iterations": 0,
        "error": None,
        "parsed_intent": {
            "product_id": req.product_id,
            "region": req.location,
            "query_type": req.proposal_type,
        },
    }

    # run_name labels the graph run in LangSmith for easy identification.
    # We look it up by run_name after the graph pauses (run_id in config is ignored by LangGraph).
    run_name = f"{req.proposal_type}:{req.product_name}"
    config = {
        "configurable": {"thread_id": thread_id},
        "run_name": run_name,
    }

    async with AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
        app = build_supervisor_graph(checkpointer=checkpointer)
        result = await _astream_until_interrupt(app, initial_state, config)

    await update_proposal_thread_id(req.proposal_id, thread_id)

    # ── Write agent results back to proposal payload columns ─────────────────
    # The graph nodes compute results and store them in graph state only.
    # Write them back to the DB so the dashboard shows real data.
    if req.proposal_type == "forecast_tuning" and result.get("proposed_tuning"):
        try:
            await update_proposal_forecast_payload(req.proposal_id, result["proposed_tuning"])
        except Exception as e:
            logger.warning(f"Failed to write forecast payload (non-fatal): {e}")

    if req.proposal_type == "replenishment" and result.get("replenishment_result"):
        try:
            await update_proposal_replenishment_payload(req.proposal_id, result["replenishment_result"])
        except Exception as e:
            logger.warning(f"Failed to write replenishment payload (non-fatal): {e}")

    if req.proposal_type == "allocation" and result.get("allocation_result"):
        try:
            await update_proposal_allocation_payload(req.proposal_id, result["allocation_result"])
        except Exception as e:
            logger.warning(f"Failed to write allocation payload (non-fatal): {e}")

    # ── LangSmith trace URL ───────────────────────────────────────────────────
    # After the graph pauses, LangSmith has already ingested the run.
    # We fetch the URL and store it on the proposal so the frontend can link to it.
    # This is a best-effort call — if LangSmith is unreachable, we skip gracefully.
    trace_id: Optional[str] = None
    trace_url: Optional[str] = None

    if _LANGSMITH_ENABLED:
        try:
            # Wait for LangSmith to ingest the run before we search for it.
            # 3s is enough in practice; the graph itself takes 2-5s so ingestion
            # is usually complete by the time we get here.
            await asyncio.sleep(3)
            trace_id, trace_url = await asyncio.get_event_loop().run_in_executor(
                None, _get_langsmith_trace_url, run_name
            )
            if trace_id:
                await update_proposal_trace_id(req.proposal_id, trace_id, trace_url)
                logger.info(f"LangSmith trace stored: id={trace_id} url={trace_url}")
            else:
                logger.warning(f"LangSmith trace not found for run_name='{run_name}'")
        except Exception as e:
            logger.warning(f"LangSmith trace capture failed (non-fatal): {e}")

    return InvokeResponse(
        thread_id=thread_id,
        proposal_id=req.proposal_id,
        status="paused_at_hitl",
        nodes_visited=result["nodes_visited"],
        agent_summary=result["agent_summary"],
        trace_id=trace_id,
        trace_url=trace_url,
    )


async def _astream_until_interrupt(app, initial_state, config) -> dict:
    """
    Stream graph events until the graph pauses (interrupt) or ends.
    Collects node names and the last AIMessage content.

    Returns dict with 'nodes_visited' and 'agent_summary'.
    """
    nodes_visited = []
    last_ai_message = "Agent analysis in progress."
    proposed_tuning = None
    replenishment_result = None
    allocation_result = None

    try:
        async for event in app.astream(initial_state, config=config, stream_mode="updates"):
            for node_name, node_output in event.items():
                if node_name == "__interrupt__":
                    # Graph paused here — this is expected
                    logger.info(f"Graph paused at interrupt for thread {config['configurable']['thread_id']}")
                    break
                nodes_visited.append(node_name)
                logger.info(f"Node completed: {node_name}")

                # Extract the last AIMessage from this node's output
                msgs = node_output.get("messages", [])
                for msg in reversed(msgs):
                    if isinstance(msg, AIMessage) and msg.content:
                        last_ai_message = msg.content
                        break

                # Capture agent results to write back to DB
                if node_output.get("proposed_tuning"):
                    proposed_tuning = node_output["proposed_tuning"]
                if node_output.get("replenishment_result"):
                    replenishment_result = node_output["replenishment_result"]
                if node_output.get("allocation_result"):
                    allocation_result = node_output["allocation_result"]

    except Exception as e:
        logger.error(f"Graph stream error: {e}", exc_info=True)
        last_ai_message = f"Agent encountered an error: {str(e)}"

    return {
        "nodes_visited": nodes_visited,
        "agent_summary": last_ai_message,
        "proposed_tuning": proposed_tuning,
        "replenishment_result": replenishment_result,
        "allocation_result": allocation_result,
    }


async def run_resume(req: ResumeRequest) -> ResumeResponse:
    """
    Resume a paused graph with the human's approval decision.

    HOW LangGraph resume works:
      1. The graph is checkpointed at interrupt_before=["hitl"]
      2. We call app.invoke(Command(resume={...}), config)
      3. LangGraph loads the checkpoint, restores state, and continues
         from where it stopped — entering hitl_node with human_response set
      4. hitl_node reads human_response, sets human_approved, routes to END

    Command(resume=value) is the LangGraph API for resuming.
    The value becomes the return value of interrupt() in hitl_node.
    """
    config = {"configurable": {"thread_id": req.thread_id}}

    resume_payload = {
        "approved": req.approved,
        "feedback": req.feedback,
    }

    async with AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
        app = build_supervisor_graph(checkpointer=checkpointer)
        result = await _astream_resume(app, resume_payload, config)

    new_status = "approved" if req.approved else "rejected"
    await update_proposal_status(req.proposal_id, new_status)

    return ResumeResponse(
        proposal_id=req.proposal_id,
        thread_id=req.thread_id,
        approved=req.approved,
        status="executed" if req.approved else "rejected",
        final_message=result["final_message"],
        nodes_visited=result["nodes_visited"],
    )


async def _astream_resume(app, resume_payload: dict, config: dict) -> dict:
    """
    Send the resume command and stream the remaining graph execution.
    """
    nodes_visited = []
    final_message = "Execution complete."

    try:
        async for event in app.astream(
            Command(resume=resume_payload),
            config=config,
            stream_mode="updates"
        ):
            for node_name, node_output in event.items():
                nodes_visited.append(node_name)
                logger.info(f"Resume — node completed: {node_name}")
                msgs = node_output.get("messages", [])
                for msg in reversed(msgs):
                    if isinstance(msg, AIMessage) and msg.content:
                        final_message = msg.content
                        break
    except Exception as e:
        logger.error(f"Resume stream error: {e}", exc_info=True)
        final_message = f"Error during execution: {str(e)}"

    return {"nodes_visited": nodes_visited, "final_message": final_message}


# ── FastAPI app ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("LangGraph agent service starting...")
    # Nothing to initialize here — SqliteSaver creates the DB on first use
    yield
    logger.info("LangGraph agent service stopped.")


app = FastAPI(
    title="Supply Chain — LangGraph Agent Service",
    version="1.0.0",
    description=(
        "HTTP wrapper around the LangGraph supervisor graph. "
        "Provides /invoke (start graph, pause at HITL) and /resume (unpause with human decision)."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # Restrict origins to known consumers instead of wildcard.
    # In production, set ALLOWED_ORIGINS env var to your actual domain(s).
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8003").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "langgraph_agent", "checkpoint_db": CHECKPOINT_DB}


@app.post("/invoke", response_model=InvokeResponse)
async def invoke_graph(req: InvokeRequest):
    """
    Start a new LangGraph supervisor run for a proposal.

    Called by monitor.py immediately after inserting a proposal row.
    The graph runs through supervisor → action node → pauses at HITL.
    Returns thread_id which is stored on the proposal for later resume.

    The graph is NON-BLOCKING here — the pause is handled by LangGraph's
    checkpoint mechanism, not by holding an HTTP connection open.
    """
    logger.info(f"Invoke: proposal={req.proposal_id} type={req.proposal_type} product={req.product_name}")
    try:
        response = await run_invoke(req)
        logger.info(
            f"Graph paused: thread_id={response.thread_id} "
            f"nodes={response.nodes_visited}"
        )
        return response
    except Exception as e:
        logger.error(f"Invoke failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Graph invocation failed: {str(e)}")


@app.post("/resume", response_model=ResumeResponse)
async def resume_graph(req: ResumeRequest):
    """
    Resume a paused graph with the human's approval decision.

    Called by the proposals router when ops manager clicks Approve/Reject.
    Looks up the checkpointed graph state by thread_id, sends the resume
    command, and streams the remaining execution to completion.

    WHY does this sometimes take 5-30 seconds?
    If approved, the graph runs:
      hitl_node → (if allocation/replenishment) A2A agent calls with polling
    A2A polling can take 10-20s if the sub-agents are doing real work.
    In production, use background tasks + websockets to stream progress.
    """
    logger.info(
        f"Resume: proposal={req.proposal_id} thread={req.thread_id} "
        f"approved={req.approved}"
    )
    try:
        response = await run_resume(req)
        logger.info(
            f"Graph completed: status={response.status} "
            f"nodes={response.nodes_visited}"
        )
        return response
    except Exception as e:
        logger.error(f"Resume failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Graph resume failed: {str(e)}")


@app.get("/threads/{thread_id}/state")
async def get_thread_state(thread_id: str):
    """
    Inspect the current state of a checkpointed graph thread.
    Useful for debugging — see what state the graph is in right now.
    """
    try:
        async with AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
            app_graph = build_supervisor_graph(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": thread_id}}
            state = await app_graph.aget_state(config)

        if state is None or not state.values:
            raise HTTPException(status_code=404, detail=f"No checkpoint found for thread_id={thread_id}")

        return {
            "thread_id": thread_id,
            "next": list(state.next),
            "values": {
                k: v for k, v in state.values.items()
                if k not in ("messages",)
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8004, reload=True, log_level="info")
