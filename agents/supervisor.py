"""
agents/supervisor.py
─────────────────────
The LangGraph Supervisor — the main orchestration graph.

CONCEPT: What is a LangGraph StateGraph?
A StateGraph is a directed graph where:
  - NODES are Python functions (your agents / tools)
  - EDGES are transitions between nodes
  - CONDITIONAL EDGES use a function to decide which node to go to next
  - The graph reads/writes shared state at every step

ARCHITECTURE OF THIS SUPERVISOR:
                    ┌─────────────┐
  user_query ──→   │  SUPERVISOR  │  (intent classification)
                    └──────┬──────┘
                           │ conditional edge (based on next_action)
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
     sql_pipeline   forecasting    allocation_replenishment
            │              │              │
            └──────────────┼──────────────┘
                           ▼
                     ┌──────────┐
                     │  HITL    │  (human approval interrupt)
                     └────┬─────┘
                          ▼
                      [DONE / END]

WHY a supervisor and not a single agent?
Different queries need fundamentally different tools and logic:
  - "Show me stock levels" → SQL insights pipeline
  - "Why is SKU-004 forecast so bad?" → Forecasting analyst
  - "Reorder the sunscreen" → Allocation + Replenishment

A single LLM call can't reliably route AND execute. The supervisor separates
ROUTING (what to do) from EXECUTION (how to do it). This is the "supervisor
pattern" — standard in production multi-agent systems.
"""

import os
import uuid
import json
import logging
import httpx
import asyncpg
from typing import Any, Optional
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt

from agents.state import SupplyChainState
from agents.sql_insights.pipeline import run_sql_insights
from agents.forecasting_analyst.analyst import run_forecasting_analyst
from agents.a2a_client import trigger_allocation, trigger_replenishment, poll_task

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://scai:scai_password@localhost:5432/supply_chain")
ALLOCATION_AGENT_URL = os.getenv("ALLOCATION_AGENT_URL", "http://localhost:8001")
REPLENISHMENT_AGENT_URL = os.getenv("REPLENISHMENT_AGENT_URL", "http://localhost:8002")

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# LLM
#
# WHY gpt-4o-mini and not gpt-4o for the supervisor?
# Intent classification is a simple task (classify into 4 categories).
# gpt-4o-mini is 10x cheaper and 2x faster for this.
# Reserve gpt-4o for complex reasoning nodes (forecasting analyst).
# ─────────────────────────────────────────────
supervisor_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0       # deterministic routing — we don't want creative routing
)

forecasting_llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0.1     # slight creativity for analysis and explanation
)


# ─────────────────────────────────────────────
# NODE 1: SUPERVISOR (intent router)
#
# This is the brain that decides what to do with each user query.
# It outputs next_action, which the conditional edge reads.
# ─────────────────────────────────────────────
async def supervisor_node(state: SupplyChainState, config: Optional[RunnableConfig] = None) -> dict:
    """
    Classify user intent and route to the appropriate sub-graph.

    INTENT CATEGORIES:
      - sql_insights: "show me revenue by region", "which products are at risk"
      - forecasting: "why is the MAPE high for SKU-004", "tune forecast models"
      - allocation: "allocate inventory to Southeast"
      - replenishment: "reorder sunscreen", "create purchase order"
      - done: "thank you", "that's all" (end conversation)
    """
    queue = config.get("configurable", {}).get("stream_queue") if config else None
    if queue:
        await queue.put({"event": "thought", "message": f"Supervisor analyzing intent for query: '{state['user_query']}'"})
    system_prompt = """You are a supply chain AI supervisor.
Your only job is to classify the user's query into one of these intents:
- sql_insights: questions about revenue, stock, orders, shipping, analytics
- forecasting: questions about forecast accuracy, MAPE, model tuning, predictions
- allocation: requests to allocate or distribute inventory
- replenishment: requests to reorder, replenish, or create purchase orders
- done: conversation endings, thank you, that's all

Respond with ONLY a JSON object: {"intent": "<intent>", "reasoning": "<one sentence>"}
Do not include any other text."""

    response = await supervisor_llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=state["user_query"])
    ])

    try:
        parsed = json.loads(response.content)
        intent = parsed.get("intent", "sql_insights")
        reasoning = parsed.get("reasoning", "")
    except json.JSONDecodeError:
        # Fallback: default to sql_insights if parsing fails
        intent = "sql_insights"
        reasoning = "Parse error, defaulting to SQL insights"

    logger.info(f"Supervisor routing: '{state['user_query']}' → {intent} ({reasoning})")

    return {
        "next_action": intent,
        "messages": [AIMessage(content=f"Routing to {intent}: {reasoning}")]
    }


# ─────────────────────────────────────────────
# NODE 2: SQL INSIGHTS PIPELINE
# ─────────────────────────────────────────────
async def sql_insights_node(state: SupplyChainState, config: Optional[RunnableConfig] = None) -> dict:
    """
    3-node sub-pipeline: Parse → SQL Gen → Format
    Returns formatted insight + raw SQL results.
    """
    queue = config.get("configurable", {}).get("stream_queue") if config else None
    if queue:
        await queue.put({"event": "thought", "message": "SQL insights node started: executing natural language to SQL pipeline..."})
    result = await run_sql_insights(
        query=state["user_query"],
        role=state.get("user_role", "analyst")
    )
    return {
        "sql_query": result["sql_query"],
        "sql_results": result["results"],
        "formatted_insight": result["insight"],
        "next_action": "hitl_check",
        "messages": [AIMessage(content=result["insight"])]
    }


# ─────────────────────────────────────────────
# NODE 3: FORECASTING ANALYST
# ─────────────────────────────────────────────
async def forecasting_node(state: SupplyChainState, config: Optional[RunnableConfig] = None) -> dict:
    """
    Research agent that reads MAPE metrics, identifies worst performers,
    and proposes hyperparameter changes. Iterates up to 2 times.
    """
    queue = config.get("configurable", {}).get("stream_queue") if config else None
    if queue:
        await queue.put({"event": "thought", "message": "Forecasting analyst node started: scanning forecast metrics to identify MAPE violations..."})
    result = await run_forecasting_analyst(
        query=state["user_query"],
        session_id=state.get("session_id", str(uuid.uuid4())),
        role=state.get("user_role", "analyst"),
        iterations=state.get("tuning_iterations", 0)
    )
    return {
        "forecast_metrics": result["metrics"],
        "worst_performers": result["worst_performers"],
        "proposed_tuning": result.get("proposed_tuning"),
        "tuning_iterations": result.get("iterations_run", 1),
        "next_action": "hitl_check",
        "messages": [AIMessage(content=result["summary"])]
    }


# ─────────────────────────────────────────────
# NODE 4: ALLOCATION + REPLENISHMENT (A2A)
#
# This node delegates work to two separate FastAPI services via A2A.
# It creates tasks, polls for completion, and collects results.
#
# WHY poll instead of await?
# The A2A services might take 10-30 seconds (they run their own logic).
# We don't want to block the supervisor's async event loop.
# Polling with exponential backoff is the A2A standard pattern.
# ─────────────────────────────────────────────
async def allocation_replenishment_node(state: SupplyChainState, config: Optional[RunnableConfig] = None) -> dict:
    """
    Delegate allocation and replenishment tasks to A2A services.
    Polls until both tasks complete or fail.
    """
    queue = config.get("configurable", {}).get("stream_queue") if config else None
    # Determine what to trigger based on original intent
    intent = state.get("next_action", "allocation")

    alloc_task_id = None
    replen_task_id = None

    if intent in ("allocation", "replenishment"):
        if queue:
            await queue.put({"event": "thought", "message": f"Triggering A2A Allocation task for SKU: {state.get('parsed_intent', {}).get('product_id')}..."})
        # Trigger allocation first
        alloc_task_id = await trigger_allocation(
            product_id=state.get("parsed_intent", {}).get("product_id"),
            region=state.get("parsed_intent", {}).get("region"),
            role=state.get("user_role", "analyst")
        )
        if queue:
            await queue.put({"event": "thought", "message": f"Allocation task triggered successfully. Task ID: {alloc_task_id}"})

    if intent == "replenishment":
        if queue:
            await queue.put({"event": "thought", "message": f"Triggering A2A Replenishment task for SKU: {state.get('parsed_intent', {}).get('product_id')}..."})
        replen_task_id = await trigger_replenishment(
            product_id=state.get("parsed_intent", {}).get("product_id"),
            role=state.get("user_role", "analyst")
        )
        if queue:
            await queue.put({"event": "thought", "message": f"Replenishment task triggered successfully. Task ID: {replen_task_id}"})

    # Poll for results
    if queue:
        await queue.put({"event": "thought", "message": "Initiating background execution task polling..."})
    alloc_result = await poll_task("allocation", alloc_task_id, config=config) if alloc_task_id else None
    replen_result = await poll_task("replenishment", replen_task_id, config=config) if replen_task_id else None

    summary_parts = []
    if alloc_result:
        summary_parts.append(f"Allocation plan: {alloc_result.get('summary', 'completed')}")
    if replen_result:
        summary_parts.append(f"Replenishment order: {replen_result.get('summary', 'completed')}")

    return {
        "allocation_task_id": alloc_task_id,
        "replenishment_task_id": replen_task_id,
        "allocation_result": alloc_result,
        "replenishment_result": replen_result,
        "next_action": "hitl_check",
        "messages": [AIMessage(content="\n".join(summary_parts))]
    }


# ─────────────────────────────────────────────
# NODE 5: HUMAN-IN-THE-LOOP (HITL)
#
# This is where LangGraph interrupt() works its magic.
#
# CONCEPT: How interrupt() works:
#   1. The graph reaches this node
#   2. interrupt() raises a special exception that LangGraph catches
#   3. The graph PAUSES and saves its current state to the checkpoint store
#   4. The API caller receives the interrupt signal + current state
#   5. The human reviews and sends back a resume command: {"approved": True}
#   6. LangGraph RESUMES from the checkpoint, calling this function again
#   7. This time, state["human_approved"] is set — we skip the interrupt()
#
# WHY checkpoint before interrupt?
# The graph might restart (crash, deploy). The checkpoint means we never
# lose work — the human can approve hours later and it still resumes correctly.
# ─────────────────────────────────────────────
async def _execute_allocation(task_id: str, allocation_result: dict | None = None) -> str:
    """
    Day 6: Call the allocation agent's /execute endpoint to apply
    inventory transfers to the DB after human approval.

    Falls back to /execute-direct (passing data from graph state) if the
    in-memory task store was cleared by a service restart.
    """
    if not task_id and not allocation_result:
        return "No allocation task to execute."
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Try task-based execute first
        if task_id:
            try:
                resp = await client.post(f"{ALLOCATION_AGENT_URL}/tasks/{task_id}/execute")
                if resp.status_code == 200:
                    return resp.json().get("message", "Allocation executed.")
                logger.warning(f"Allocation task execute returned {resp.status_code} — falling back to direct execute")
            except Exception as e:
                logger.warning(f"Allocation task execute failed: {e} — falling back to direct execute")

        # Fallback: send plan data directly from graph state
        if allocation_result:
            plan = allocation_result.get("allocation_plan", [])
            if not plan:
                return "No allocation transfers to apply."
            try:
                resp = await client.post(
                    f"{ALLOCATION_AGENT_URL}/execute-direct",
                    json={"allocation_plan": plan}
                )
                resp.raise_for_status()
                return resp.json().get("message", "Allocation executed via direct payload.")
            except Exception as e:
                logger.error(f"Allocation direct execute failed: {e}")
                return f"Allocation execute error: {str(e)}"

    return "Allocation execute: no data available."


async def _execute_replenishment(task_id: str, replenishment_result: dict | None = None) -> str:
    """
    Day 6: Call the replenishment agent's /execute endpoint to insert
    purchase orders and update inventory stock levels after human approval.

    Falls back to /execute-direct (passing data from graph state) if the
    in-memory task store was cleared by a service restart.
    """
    if not task_id and not replenishment_result:
        return "No replenishment task to execute."
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Try task-based execute first
        if task_id:
            try:
                resp = await client.post(f"{REPLENISHMENT_AGENT_URL}/tasks/{task_id}/execute")
                if resp.status_code == 200:
                    return resp.json().get("message", "Replenishment executed.")
                logger.warning(f"Replenishment task execute returned {resp.status_code} — falling back to direct execute")
            except Exception as e:
                logger.warning(f"Replenishment task execute failed: {e} — falling back to direct execute")

        # Fallback: send PO data directly from graph state
        if replenishment_result:
            pos = replenishment_result.get("purchase_orders", [])
            if not pos:
                return "No purchase orders to apply."
            try:
                resp = await client.post(
                    f"{REPLENISHMENT_AGENT_URL}/execute-direct",
                    json={"purchase_orders": pos}
                )
                resp.raise_for_status()
                return resp.json().get("message", "Replenishment executed via direct payload.")
            except Exception as e:
                logger.error(f"Replenishment direct execute failed: {e}")
                return f"Replenishment execute error: {str(e)}"

    return "Replenishment execute: no data available."


async def _execute_forecast_tuning(state: SupplyChainState) -> str:
    """
    Day 6+7: Apply approved hyperparameter changes to the forecast_metrics table,
    log the change in hyperparameter_tuning_log, and simulate drift detection
    by inserting a new forecast_metrics row with an estimated post-tuning MAPE.
    """
    import json as _json
    import random
    from datetime import date

    proposed = state.get("proposed_tuning")
    if not proposed:
        return "No forecast tuning changes to apply."

    try:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
        try:
            async with pool.acquire() as conn:
                worst = state.get("worst_performers", [])
                product_id = worst[0].get("product_id") if worst else None
                # Fallback: use target_product_id from proposed_tuning
                if not product_id:
                    product_id = proposed.get("target_product_id")

                if not product_id or not proposed.get("new_params"):
                    return "No product_id or new_params found — skipping."

                new_params = _json.dumps(proposed["new_params"])
                old_params = _json.dumps(proposed.get("old_params", {}))

                # Get current MAPE (pre-tuning)
                pre_mape_row = await conn.fetchrow("""
                    SELECT mape, model_name FROM forecast_metrics
                    WHERE product_id = $1
                    ORDER BY run_date DESC LIMIT 1
                """, product_id)
                pre_mape = float(pre_mape_row["mape"]) if pre_mape_row else None
                model_name = pre_mape_row["model_name"] if pre_mape_row else "xgboost_v1"

                # Update hyperparameters on the most recent model run
                await conn.execute("""
                    UPDATE forecast_metrics
                    SET hyperparameters = $1::jsonb
                    WHERE product_id = $2
                    AND run_date = (
                        SELECT MAX(run_date) FROM forecast_metrics WHERE product_id = $2
                    )
                """, new_params, product_id)

                # ── Day 7: Drift detection ────────────────────────────────────────
                # Simulate post-tuning MAPE: apply a random improvement of 5-15%.
                # In production: re-run the model with new_params on validation data.
                post_mape = None
                mape_delta = None
                if pre_mape is not None:
                    improvement_factor = random.uniform(0.05, 0.15)
                    post_mape = round(pre_mape * (1 - improvement_factor), 4)
                    mape_delta = round(pre_mape - post_mape, 4)

                    # Insert a new forecast_metrics row reflecting the post-tuning run
                    today = date.today()
                    await conn.execute("""
                        INSERT INTO forecast_metrics
                            (product_id, model_name, mape, run_date, hyperparameters, notes)
                        VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                        ON CONFLICT DO NOTHING
                    """,
                        product_id,
                        model_name,
                        post_mape,
                        today,
                        new_params,
                        f"Post-tuning run (simulated). Pre-tuning MAPE: {pre_mape:.4f}. Delta: -{mape_delta:.4f}."
                    )
                    logger.info(f"Drift check: {product_id} MAPE {pre_mape:.4f} → {post_mape:.4f} (Δ {mape_delta:.4f})")

                # Log the change with drift data
                await conn.execute("""
                    INSERT INTO hyperparameter_tuning_log
                        (product_id, old_params, new_params, rationale, status,
                         pre_mape, post_mape, mape_delta, simulated, evaluated_at)
                    VALUES ($1, $2::jsonb, $3::jsonb, $4, 'approved',
                            $5, $6, $7, TRUE, NOW())
                """,
                    product_id,
                    old_params,
                    new_params,
                    proposed.get("rationale", "Approved via HITL dashboard"),
                    pre_mape,
                    post_mape,
                    mape_delta,
                )

                improvement_str = f"MAPE {pre_mape:.1%} → {post_mape:.1%} (Δ {mape_delta:.1%})" if post_mape else "N/A"
                return (
                    f"Hyperparameters updated for {product_id}. "
                    f"Drift check: {improvement_str}. "
                    f"Expected: {proposed.get('expected_mape_improvement', 'N/A')}."
                )
        finally:
            await pool.close()
    except Exception as e:
        logger.error(f"Forecast tuning execute failed: {e}", exc_info=True)
        return f"Forecast tuning execute error: {str(e)}"

    return "No changes applied."


async def _execute_supplier_config(state: SupplyChainState, config: Optional[RunnableConfig] = None) -> str:
    """
    Apply approved supplier configuration updates to the suppliers table in PostgreSQL,
    and trigger the Git PR Agent to create a PR tracking the configuration update.
    """
    import json as _json
    queue = config.get("configurable", {}).get("stream_queue") if config else None
    payload = state.get("supplier_config_payload")

    if not payload:
        return "Supplier config execute: no payload found."

    supplier_id = payload.get("supplier_id")
    supplier_name = payload.get("supplier_name", "Supplier")
    lead_time_days = payload.get("lead_time_days")
    defect_rate = payload.get("defect_rate")
    proposal_id = state.get("proposal_id", "")

    if not supplier_id or lead_time_days is None or defect_rate is None:
        return "Supplier config execute: invalid payload data."

    try:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
        try:
            async with pool.acquire() as conn:
                if queue:
                    await queue.put({"event": "thought", "message": f"Updating database record for supplier {supplier_name} ({supplier_id})..."})
                
                # Update PostgreSQL suppliers table
                await conn.execute("""
                    UPDATE suppliers
                    SET lead_time_days = $1, defect_rate = $2
                    WHERE supplier_id = $3
                """, lead_time_days, defect_rate, supplier_id)

                if queue:
                    await queue.put({"event": "thought", "message": "Database record updated. Launching GitHub PR Agent..."})

                # Trigger Git PR Agent
                from agents.git_pr_agent import create_github_pr
                pr_result = await create_github_pr(
                    supplier_id=supplier_id,
                    supplier_name=supplier_name,
                    lead_time_days=lead_time_days,
                    defect_rate=defect_rate,
                    queue=queue
                )

                if pr_result.get("success"):
                    pr_url = pr_result.get("pr_url")
                    
                    # Update proposal's supplier_config_payload to store the created branch and pr_url
                    updated_payload = dict(payload)
                    updated_payload["branch_name"] = pr_result.get("branch_name")
                    updated_payload["pr_url"] = pr_url
                    
                    if proposal_id:
                        await conn.execute("""
                            UPDATE proposals
                            SET supplier_config_payload = $1::jsonb
                            WHERE id = $2
                        """, _json.dumps(updated_payload), proposal_id)
                    else:
                        await conn.execute("""
                            UPDATE proposals
                            SET supplier_config_payload = $1::jsonb
                            WHERE supplier_config_payload->>'supplier_id' = $2
                            AND status = 'pending'
                        """, _json.dumps(updated_payload), supplier_id)
                    
                    return f"Updated supplier {supplier_name} configurations. Branch: {pr_result.get('branch_name')}. PR Link generated."
                else:
                    return f"Updated supplier {supplier_name} configurations in DB, but Git failed: {pr_result.get('error')}"
        finally:
            await pool.close()
    except Exception as e:
        logger.error(f"Supplier config execute failed: {e}", exc_info=True)
        return f"Supplier config execute error: {str(e)}"


async def hitl_node(state: SupplyChainState, config: Optional[RunnableConfig] = None) -> dict:
    """
    Pause and wait for human approval before taking any 'action'.

    Day 6 addition: after approval, call the appropriate execute function
    to actually write changes to the database.
    """
    queue = config.get("configurable", {}).get("stream_queue") if config else None
    # ── Fallback for re-running node from beginning (if human_approved is already set)
    if state.get("human_approved") is not None:
        user_role = state.get("user_role", "analyst")
        if state["human_approved"]:
            if user_role != "admin":
                return {
                    "next_action": "done",
                    "messages": [AIMessage(content="Permission denied: Only administrator role can execute changes.")]
                }
            execution_messages = []

            alloc_task_id = state.get("allocation_task_id")
            replen_task_id = state.get("replenishment_task_id")
            intent = state.get("parsed_intent", {}).get("query_type", "")

            if alloc_task_id or state.get("allocation_result"):
                if queue:
                    await queue.put({"event": "thought", "message": "Executing approved Inventory Transfer transfers in DB..."})
                msg = await _execute_allocation(alloc_task_id, state.get("allocation_result"))
                execution_messages.append(f"Allocation: {msg}")

            if replen_task_id or state.get("replenishment_result"):
                if queue:
                    await queue.put({"event": "thought", "message": "Executing approved Purchase Order in DB..."})
                msg = await _execute_replenishment(replen_task_id, state.get("replenishment_result"))
                execution_messages.append(f"Replenishment: {msg}")

            if intent == "forecast_tuning" or state.get("proposed_tuning"):
                if queue:
                    await queue.put({"event": "thought", "message": "Applying forecasting hyperparameter retuning changes..."})
                msg = await _execute_forecast_tuning(state)
                execution_messages.append(f"Forecast tuning: {msg}")

            if intent == "supplier_config" or state.get("supplier_config_payload"):
                if queue:
                    await queue.put({"event": "thought", "message": "Applying supplier configuration changes..."})
                msg = await _execute_supplier_config(state, config)
                execution_messages.append(f"Supplier config: {msg}")

            summary = " | ".join(execution_messages) if execution_messages else "Action approved and executed."
            if queue:
                await queue.put({"event": "thought", "message": f"Execution finished successfully: {summary}"})
            return {
                "next_action": "done",
                "messages": [AIMessage(content=summary)]
            }
        else:
            if queue:
                await queue.put({"event": "thought", "message": f"Action rejected: {state.get('human_feedback', 'No reason given')}"})
            return {
                "next_action": "done",
                "messages": [AIMessage(content=f"Action rejected. Reason: {state.get('human_feedback', 'No reason given')}.")]
            }

    # Prepare the approval request payload — shown to the human
    approval_request = {
        "pending_action": state.get("next_action"),
        "proposed_tuning": state.get("proposed_tuning"),
        "allocation_result": state.get("allocation_result"),
        "replenishment_result": state.get("replenishment_result"),
        "supplier_config_payload": state.get("supplier_config_payload"),
        "message": "Review the proposed action and approve or reject."
    }

    # Pause the graph here — resumes when human sends Command(resume=...)
    human_response = interrupt(approval_request)

    approved = human_response.get("approved", False)
    feedback = human_response.get("feedback", "")
    user_role = human_response.get("user_role", state.get("user_role", "analyst"))

    if queue:
        action_str = "APPROVED" if approved else "REJECTED"
        await queue.put({"event": "thought", "message": f"HITL decision received: {action_str}"})

    if approved:
        # Enforce role verification on immediate execution path
        if user_role != "admin":
            if queue:
                await queue.put({"event": "thought", "message": "Permission denied: Only administrator role can execute changes."})
            return {
                "human_approved": False,
                "human_feedback": "Permission denied: Only administrator role can execute changes.",
                "user_role": user_role,
                "next_action": "done",
                "messages": [AIMessage(content="Permission denied: Only administrator role can execute changes.")]
            }

        execution_messages = []
        alloc_task_id = state.get("allocation_task_id")
        replen_task_id = state.get("replenishment_task_id")
        intent = state.get("parsed_intent", {}).get("query_type", "")

        if alloc_task_id or state.get("allocation_result"):
            if queue:
                await queue.put({"event": "thought", "message": "Applying Inventory Transfer in database..."})
            msg = await _execute_allocation(alloc_task_id, state.get("allocation_result"))
            execution_messages.append(f"Allocation: {msg}")

        if replen_task_id or state.get("replenishment_result"):
            if queue:
                await queue.put({"event": "thought", "message": "Applying Purchase Order in database..."})
            msg = await _execute_replenishment(replen_task_id, state.get("replenishment_result"))
            execution_messages.append(f"Replenishment: {msg}")

        if intent == "forecast_tuning" or state.get("proposed_tuning"):
            if queue:
                await queue.put({"event": "thought", "message": "Applying forecast hyperparameter changes..."})
            msg = await _execute_forecast_tuning(state)
            execution_messages.append(f"Forecast tuning: {msg}")

        if intent == "supplier_config" or state.get("supplier_config_payload"):
            if queue:
                await queue.put({"event": "thought", "message": "Applying supplier configuration changes..."})
            msg = await _execute_supplier_config(state, config)
            execution_messages.append(f"Supplier config: {msg}")

        summary = " | ".join(execution_messages) if execution_messages else "Action approved and executed."
        if queue:
            await queue.put({"event": "thought", "message": f"Execution finished successfully: {summary}"})
        return {
            "human_approved": approved,
            "human_feedback": feedback,
            "user_role": user_role,
            "next_action": "done",
            "messages": [AIMessage(content=summary)]
        }
    else:
        if queue:
            await queue.put({"event": "thought", "message": f"Action rejected: {feedback or 'No reason given'}"})
        return {
            "human_approved": approved,
            "human_feedback": feedback,
            "user_role": user_role,
            "next_action": "done",
            "messages": [AIMessage(content=f"Action rejected. Reason: {feedback or 'No reason given'}.")]
        }


# ─────────────────────────────────────────────
# ROUTING FUNCTION
#
# This is the function used by add_conditional_edges().
# It reads state["next_action"] and returns the name of the next node.
# ─────────────────────────────────────────────
def route_supervisor(state: SupplyChainState) -> str:
    """Determine which node to route to based on supervisor's decision."""
    action = state.get("next_action", "sql_insights")
    if action == "done":
        return END
    routing_map = {
        "sql_insights": "sql_insights",
        "forecasting": "forecasting",
        "allocation": "allocation_replenishment",
        "replenishment": "allocation_replenishment",
    }
    return routing_map.get(action, "sql_insights")


def route_after_action(state: SupplyChainState) -> str:
    """After any action node completes, go to HITL."""
    return "hitl"


def route_after_hitl(state: SupplyChainState) -> str:
    """After HITL, done."""
    return END


# ─────────────────────────────────────────────
# BUILD THE GRAPH
# ─────────────────────────────────────────────
def build_supervisor_graph(checkpointer=None):
    """
    Construct and compile the supervisor StateGraph.

    WHY compile()? LangGraph validates the graph structure at compile time —
    catches unreachable nodes, missing edges, etc. It also prepares the
    graph for async execution and checkpointing.

    Args:
        checkpointer: A LangGraph checkpointer (e.g., SqliteSaver).
                      If None, graph runs without persistence.

    Returns:
        Compiled LangGraph app (callable)
    """
    graph = StateGraph(SupplyChainState)

    # Add all nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("sql_insights", sql_insights_node)
    graph.add_node("forecasting", forecasting_node)
    graph.add_node("allocation_replenishment", allocation_replenishment_node)
    graph.add_node("hitl", hitl_node)

    # Entry point: always start at supervisor
    graph.add_edge(START, "supervisor")

    # Conditional routing from supervisor
    graph.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {
            "sql_insights": "sql_insights",
            "forecasting": "forecasting",
            "allocation_replenishment": "allocation_replenishment",
            END: END
        }
    )

    # After each action, go to HITL
    graph.add_edge("sql_insights", "hitl")
    graph.add_edge("forecasting", "hitl")
    graph.add_edge("allocation_replenishment", "hitl")

    # After HITL, end
    graph.add_edge("hitl", END)

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["hitl"]   # LangGraph will auto-interrupt BEFORE hitl node runs
                                    # This means we pause before showing results to human,
                                    # giving them a chance to review the intermediate state
    )


# ─────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────
async def run_supervisor(user_query: str, user_role: str = "analyst", session_id: str = None):
    """
    Run the supervisor graph for a single user query.

    Args:
        user_query: The user's natural language question
        user_role: 'analyst' or 'admin' — determines MCP tool permissions
        session_id: For checkpointing. If None, generates a new UUID.

    Yields:
        Streaming updates from each node as they complete.
    """
    if session_id is None:
        session_id = str(uuid.uuid4())

    # SQLite checkpointer — stores graph state so we can resume after interrupt()
    # In production: use PostgresSaver (asyncpg-based) for multi-instance deployments
    with SqliteSaver.from_conn_string("supply_chain_checkpoints.db") as checkpointer:
        app = build_supervisor_graph(checkpointer=checkpointer)

        config = {
            "configurable": {
                "thread_id": session_id   # thread_id scopes the checkpoint to this session
            }
        }

        initial_state = {
            "user_query": user_query,
            "user_role": user_role,
            "session_id": session_id,
            "messages": [HumanMessage(content=user_query)],
            "human_approved": None,
            "tuning_iterations": 0,
            "error": None
        }

        # Stream events from the graph
        async for event in app.astream_events(initial_state, config=config, version="v2"):
            yield event
