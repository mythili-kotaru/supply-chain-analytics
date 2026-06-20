"""
mcp_server/server.py
─────────────────────
The FastMCP server. This is the central tool API for all agents.

WHY FastMCP and not building MCP from scratch?
MCP (Model Context Protocol) is a spec — FastMCP is a Python framework that
implements the spec with minimal boilerplate. Anthropic open-sourced it.

The key abstraction: you decorate a Python function with @mcp.tool() and
FastMCP handles:
  - JSON schema generation from type hints
  - Request routing (tool call → function call)
  - Response serialization back to MCP format
  - SSE (Server-Sent Events) transport for streaming

MCP standardizes how AI agents call tools. Any MCP-compatible client
(Claude, LangChain, LangGraph via langchain-mcp-adapters) can call this
server without knowing its internals. It's the "USB-C for AI tools" pattern.

Architecture of this file:
  1. Middleware: RBAC check on every tool call (before the function runs)
  2. Tools: hybrid_search, inventory_lookup, entity_resolve, submit_recommendation
  3. Server startup: uvicorn on port 8000
"""

import os
import time
import logging
from contextlib import asynccontextmanager

import asyncpg
import openai
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from middleware.rbac import RBACMiddleware, require_role
from tools.hybrid_search import hybrid_search_impl
from tools.inventory import inventory_lookup_impl
from tools.entity_resolve import entity_resolve_impl
from tools.recommendations import submit_recommendation_impl

# ─────────────────────────────────────────────
# LOGGING
# Production would use structured JSON logging (structlog or python-json-logger)
# For now, standard logging is fine.
# ─────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# DATABASE CONNECTION POOL
#
# WHY asyncpg and not psycopg2?
# FastMCP is async (built on Starlette/uvicorn).
# asyncpg is the high-performance async Postgres driver.
# psycopg2 is blocking — it would stall the event loop.
#
# WHY a pool and not a single connection?
# Multiple tool calls can arrive concurrently. A pool (min=2, max=10) means
# each concurrent request gets its own connection without waiting.
# ─────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://scai:scai_password@localhost:5432/supply_chain")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

db_pool: asyncpg.Pool | None = None
openai_client: openai.AsyncOpenAI | None = None


@asynccontextmanager
async def lifespan(app):
    """
    Lifespan context manager: runs setup on startup, teardown on shutdown.

    WHY lifespan instead of just creating the pool at module level?
    Module-level async code doesn't work cleanly with uvicorn's event loop.
    Lifespan guarantees the pool is ready before any requests arrive.
    """
    global db_pool, openai_client

    logger.info("Starting MCP server — initializing DB pool...")
    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2,
        max_size=10,
        command_timeout=30       # fail fast if DB is unresponsive
    )
    openai_client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
    logger.info("DB pool ready. MCP server running.")

    yield  # server is live here

    logger.info("Shutting down — closing DB pool...")
    await db_pool.close()


# ─────────────────────────────────────────────
# CREATE THE MCP SERVER
#
# FastMCP(name=...) creates the server instance.
# The name appears in the MCP manifest — clients use it to identify the server.
# ─────────────────────────────────────────────
mcp = FastMCP(
    name="supply-chain-mcp",
    lifespan=lifespan
)

# ─────────────────────────────────────────────
# RBAC MIDDLEWARE
#
# Every tool call passes through this before the tool function runs.
# The middleware reads the 'x-role' header from the request:
#   - 'analyst': can call read-only tools
#   - 'admin': can call all tools including submit_recommendation
#
# WHY headers and not API keys?
# In a real system you'd verify a JWT and extract the role from claims.
# For this project, we simulate it with a simple header.
# The RBAC logic itself (role → allowed tools) is what interviewers care about.
# ─────────────────────────────────────────────
mcp.add_middleware(RBACMiddleware)

# ─────────────────────────────────────────────
# ASGI APP
#
# FastMCP v3.x no longer exposes a bare ASGI callable on the FastMCP object.
# mcp.http_app() returns the underlying Starlette app that uvicorn can serve.
# We also mount /tools (list) and /health endpoints via the HTTP app.
# ─────────────────────────────────────────────
app = mcp.http_app()

from starlette.responses import JSONResponse

async def health_check(request):
    return JSONResponse({"status": "healthy"})

app.add_route("/health", health_check)


# ─────────────────────────────────────────────
# TOOL 1: hybrid_search
#
# The flagship tool — combines vector similarity + full-text search.
# This is what makes your MCP server genuinely useful vs. a simple SQL proxy.
#
# HOW HYBRID SEARCH WORKS:
#
# Step 1: Vector search
#   Embed the query with OpenAI → get a 1536-dim vector
#   Run: SELECT record_id, 1 - (embedding <=> $1) AS score FROM supply_chain_records
#        ORDER BY embedding <=> $1 LIMIT 20
#   <=> is cosine distance. 1 - distance = cosine similarity.
#   Result: top-20 semantically similar records
#
# Step 2: Full-text search (BM25-like)
#   Run: SELECT record_id, ts_rank(search_vector, query) AS score
#        FROM supply_chain_records
#        WHERE search_vector @@ to_tsquery('english', $1)
#   Result: top-20 keyword-matching records
#
# Step 3: Reciprocal Rank Fusion (RRF)
#   Each result gets a score: 1 / (rank + 60)
#   Sum RRF scores from both lists for records appearing in either list
#   Sort by combined RRF score
#   WHY RRF? It handles the "different scales" problem — vector scores are
#   0-1 floats, BM25 scores are unbounded. RRF normalizes by rank position.
# ─────────────────────────────────────────────
@mcp.tool()
async def hybrid_search(
    query: str,
    region: str | None = None,
    category: str | None = None,
    limit: int = 10,
    role: str = "analyst"   # injected by RBAC middleware (see middleware/rbac.py)
) -> dict:
    """
    Search supply chain records using hybrid vector + full-text search.

    Args:
        query: Natural language search query (e.g. "sunscreen stockout risk")
        region: Optional filter by region (Northeast, Southeast, West, Midwest)
        category: Optional filter by category (skincare, haircare, cosmetics)
        limit: Max results to return (default 10, max 50)
        role: Caller role — injected by middleware, do not set manually

    Returns:
        dict with 'results' list and 'metadata' (latency, result_count)
    """
    start = time.monotonic()

    # Delegate to the implementation function (keeps this file readable)
    results = await hybrid_search_impl(
        db_pool=db_pool,
        openai_client=openai_client,
        query=query,
        region=region,
        category=category,
        limit=min(limit, 50)   # cap at 50 to prevent abuse
    )

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(f"hybrid_search: {len(results)} results in {elapsed_ms:.1f}ms")

    return {
        "results": results,
        "metadata": {
            "result_count": len(results),
            "latency_ms": round(elapsed_ms, 1),
            "query": query
        }
    }


# ─────────────────────────────────────────────
# TOOL 2: inventory_lookup
#
# Simple but important: check current stock vs. reorder point.
# The Allocation Agent calls this before computing an allocation plan.
# ─────────────────────────────────────────────
@mcp.tool()
async def inventory_lookup(
    product_id: str | None = None,
    location: str | None = None,
    below_reorder_only: bool = False,
    role: str = "analyst"
) -> dict:
    """
    Look up current inventory levels.

    Args:
        product_id: Filter by specific product (e.g. 'SKU-001'). None = all products.
        location: Filter by location/region. None = all locations.
        below_reorder_only: If True, only return items where stock < reorder_point.
        role: Caller role — injected by middleware

    Returns:
        dict with 'inventory' list showing stock levels and reorder status
    """
    start = time.monotonic()
    require_role(role, allowed=["analyst", "admin"])  # both roles can read inventory

    result = await inventory_lookup_impl(
        db_pool=db_pool,
        product_id=product_id,
        location=location,
        below_reorder_only=below_reorder_only
    )

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(f"inventory_lookup: {len(result)} rows in {elapsed_ms:.1f}ms")

    return {
        "inventory": result,
        "metadata": {"latency_ms": round(elapsed_ms, 1), "row_count": len(result)}
    }


# ─────────────────────────────────────────────
# TOOL 3: entity_resolve
#
# "Entity resolution" = figuring out which DB record a fuzzy name refers to.
# Example: user says "SPF cream" → resolve to product_id SKU-008 (Sunscreen SPF50)
#
# HOW it works:
#   1. Embed the fuzzy name with OpenAI
#   2. Run vector similarity search against product names
#   3. Return top-3 candidates with confidence scores
#
# WHY this matters:
# LLMs hallucinate product IDs. Entity resolution grounds them.
# The agent sends the user's natural language term; we return the canonical ID.
# ─────────────────────────────────────────────
@mcp.tool()
async def entity_resolve(
    entity_name: str,
    entity_type: str = "product",   # 'product' | 'supplier' | 'location'
    role: str = "analyst"
) -> dict:
    """
    Resolve a fuzzy entity name to a canonical database ID.

    Args:
        entity_name: The fuzzy name to resolve (e.g. 'SPF cream', 'Mumbai supplier')
        entity_type: Type of entity to search ('product', 'supplier', 'location')
        role: Caller role — injected by middleware

    Returns:
        dict with 'candidates' list (id, name, confidence_score) and best match
    """
    require_role(role, allowed=["analyst", "admin"])

    result = await entity_resolve_impl(
        db_pool=db_pool,
        openai_client=openai_client,
        entity_name=entity_name,
        entity_type=entity_type
    )
    return result


# ─────────────────────────────────────────────
# TOOL 4: submit_recommendation
#
# ADMIN ONLY — this writes to the DB (hyperparameter_tuning_log).
# The Forecasting Analyst agent calls this to log its proposed changes.
# Human approval happens via LangGraph interrupt() before this is called.
#
# WHY separate from the other tools?
# It mutates state. Analysts should never be able to trigger DB writes.
# RBAC enforces this at the tool level — even if an analyst's prompt
# somehow routes here, the middleware blocks it.
# ─────────────────────────────────────────────
@mcp.tool()
async def submit_recommendation(
    product_id: str,
    old_params: dict,
    new_params: dict,
    rationale: str,
    agent_run_id: str,
    role: str = "analyst"   # will be rejected unless 'admin'
) -> dict:
    """
    Submit a hyperparameter tuning recommendation (ADMIN ONLY).

    Args:
        product_id: Which product's forecast model to tune
        old_params: Current hyperparameter values (from forecast_metrics)
        new_params: Proposed new values
        rationale: Agent's explanation for the change
        agent_run_id: LangGraph run_id for traceability
        role: Must be 'admin'

    Returns:
        dict with 'log_id' of the created tuning log entry
    """
    require_role(role, allowed=["admin"])   # analyst will get PermissionError here

    result = await submit_recommendation_impl(
        db_pool=db_pool,
        product_id=product_id,
        old_params=old_params,
        new_params=new_params,
        rationale=rationale,
        agent_run_id=agent_run_id
    )
    return result


# ─────────────────────────────────────────────
# START THE SERVER
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    # FastMCP.run() wraps uvicorn for you, but calling uvicorn directly
    # gives you more control over workers, reload, etc.
    uvicorn.run(
        "server:app",           # module:app_variable — use the ASGI http_app, not the FastMCP object
        host="0.0.0.0",         # bind to all interfaces (needed in Docker)
        port=8000,
        reload=True,            # hot reload during dev (disable in prod)
        log_level="info"
    )
