"""
agents/state.py
────────────────
The shared state type for the entire LangGraph supervisor graph.

WHY typed state?
LangGraph is a state machine. Every node reads from and writes to a shared
state object. TypedDict + Annotated gives you:
  1. Type safety — you catch bugs at definition time, not runtime
  2. Merge semantics — Annotated[list, add_messages] tells LangGraph HOW
     to merge state when two parallel nodes both write to the same field.

CONCEPT: What is LangGraph state?
Imagine state as a whiteboard that all agents share.
  - Supervisor writes: "user_intent = 'inventory_query'"
  - SQL agent reads user_intent, writes: "sql_results = [...]"
  - Forecasting agent reads sql_results, writes: "forecast_analysis = {...}"
  - Supervisor reads all results, writes: "final_response = '...'"

State flows through the graph. Each node is a function:
  def my_node(state: SupplyChainState) -> dict:
      # read from state
      # do work
      # return dict of fields to update in state

WHY not just pass arguments between functions?
Because with state, you can:
  - Checkpoint at any node (SQLite persistence)
  - Resume from any checkpoint (HITL interrupt/resume)
  - Fan out to parallel nodes and merge results
  - Inspect the full history of what happened at each step
"""

from typing import Annotated, Any
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class SupplyChainState(TypedDict):
    """
    The complete shared state for the Supply Chain AI supervisor graph.

    Every field here is readable/writable by every node.
    Convention: nodes only write to fields they "own".
    """

    # ─────────────────────────────────────────────
    # CONVERSATION HISTORY
    #
    # Annotated[list, add_messages] is special LangGraph syntax.
    # It tells the graph: when merging state updates, APPEND to this list
    # instead of REPLACING it. Without this, each node would wipe the
    # message history.
    #
    # BaseMessage is LangChain's base class for HumanMessage, AIMessage,
    # ToolMessage, SystemMessage.
    # ─────────────────────────────────────────────
    messages: Annotated[list[BaseMessage], add_messages]

    # ─────────────────────────────────────────────
    # ROUTING
    #
    # The supervisor determines intent and sets this field.
    # Conditional edges read it to decide which node to route to.
    # Possible values: 'sql_insights', 'forecasting', 'allocation', 'replenishment', 'done'
    # ─────────────────────────────────────────────
    next_action: str

    # ─────────────────────────────────────────────
    # USER CONTEXT
    # ─────────────────────────────────────────────
    user_query: str           # raw query from the user
    user_role: str            # 'analyst' or 'admin' — passed to MCP server headers
    session_id: str           # for checkpointing and LangSmith tracing

    # ─────────────────────────────────────────────
    # SQL INSIGHTS PIPELINE OUTPUT
    # ─────────────────────────────────────────────
    parsed_intent: dict[str, Any]    # output of the Query Parser node
    sql_query: str                    # generated SQL query
    sql_results: list[dict]           # raw query results
    formatted_insight: str            # human-readable summary

    # ─────────────────────────────────────────────
    # FORECASTING ANALYST OUTPUT
    # ─────────────────────────────────────────────
    forecast_metrics: list[dict]      # MAPE data per product
    worst_performers: list[dict]      # products with MAPE > threshold
    proposed_tuning: dict[str, Any]   # hyperparameter change proposal
    tuning_iterations: int            # how many auto-tune loops have run

    # ─────────────────────────────────────────────
    # ALLOCATION / REPLENISHMENT
    # ─────────────────────────────────────────────
    allocation_task_id: str           # A2A task ID from Allocation Agent
    replenishment_task_id: str        # A2A task ID from Replenishment Agent
    allocation_result: dict[str, Any]
    replenishment_result: dict[str, Any]

    # ─────────────────────────────────────────────
    # HUMAN-IN-THE-LOOP
    #
    # human_approved is set to None initially.
    # LangGraph interrupt() pauses here and waits.
    # When the human approves/rejects, this is set and the graph resumes.
    # ─────────────────────────────────────────────
    human_approved: bool | None       # None = pending approval
    human_feedback: str               # optional text from the approver

    # ─────────────────────────────────────────────
    # ERROR TRACKING
    # ─────────────────────────────────────────────
    error: str | None                 # set if any node fails
