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
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt

from agents.state import SupplyChainState
from agents.sql_insights.pipeline import run_sql_insights
from agents.forecasting_analyst.analyst import run_forecasting_analyst
from agents.a2a_client import trigger_allocation, trigger_replenishment, poll_task

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
async def supervisor_node(state: SupplyChainState) -> dict:
    """
    Classify user intent and route to the appropriate sub-graph.

    INTENT CATEGORIES:
      - sql_insights: "show me revenue by region", "which products are at risk"
      - forecasting: "why is the MAPE high for SKU-004", "tune forecast models"
      - allocation: "allocate inventory to Southeast"
      - replenishment: "reorder sunscreen", "create purchase order"
      - done: "thank you", "that's all" (end conversation)
    """
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
async def sql_insights_node(state: SupplyChainState) -> dict:
    """
    3-node sub-pipeline: Parse → SQL Gen → Format
    Returns formatted insight + raw SQL results.
    """
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
async def forecasting_node(state: SupplyChainState) -> dict:
    """
    Research agent that reads MAPE metrics, identifies worst performers,
    and proposes hyperparameter changes. Iterates up to 2 times.
    """
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
async def allocation_replenishment_node(state: SupplyChainState) -> dict:
    """
    Delegate allocation and replenishment tasks to A2A services.
    Polls until both tasks complete or fail.
    """
    # Determine what to trigger based on original intent
    intent = state.get("next_action", "allocation")

    alloc_task_id = None
    replen_task_id = None

    if intent in ("allocation", "replenishment"):
        # Trigger allocation first
        alloc_task_id = await trigger_allocation(
            product_id=state.get("parsed_intent", {}).get("product_id"),
            region=state.get("parsed_intent", {}).get("region"),
            role=state.get("user_role", "analyst")
        )

    if intent == "replenishment":
        replen_task_id = await trigger_replenishment(
            product_id=state.get("parsed_intent", {}).get("product_id"),
            role=state.get("user_role", "analyst")
        )

    # Poll for results
    alloc_result = await poll_task("allocation", alloc_task_id) if alloc_task_id else None
    replen_result = await poll_task("replenishment", replen_task_id) if replen_task_id else None

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
async def hitl_node(state: SupplyChainState) -> dict:
    """
    Pause and wait for human approval before taking any 'action'
    (submitting recommendations, triggering allocation/replenishment).
    """
    # If already approved, skip the interrupt
    if state.get("human_approved") is not None:
        if state["human_approved"]:
            return {"next_action": "done", "messages": [AIMessage(content="Action approved and executed.")]}
        else:
            return {"next_action": "done", "messages": [AIMessage(content=f"Action rejected. Reason: {state.get('human_feedback', 'No reason given')}.")]}

    # Prepare the approval request payload — shown to the human
    approval_request = {
        "pending_action": state.get("next_action"),
        "proposed_tuning": state.get("proposed_tuning"),
        "allocation_result": state.get("allocation_result"),
        "replenishment_result": state.get("replenishment_result"),
        "message": "Review the proposed action and approve or reject."
    }

    # THIS IS THE KEY LINE: interrupt() pauses the graph here.
    # The dict passed to interrupt() is sent back to the caller.
    # When the graph resumes, human_response is the value passed back in.
    human_response = interrupt(approval_request)

    # When we get here, the human has responded
    approved = human_response.get("approved", False)
    feedback = human_response.get("feedback", "")

    return {
        "human_approved": approved,
        "human_feedback": feedback,
        "next_action": "done" if approved else "done"
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
