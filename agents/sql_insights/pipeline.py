"""
agents/sql_insights/pipeline.py
─────────────────────────────────
3-node SQL insights pipeline:
  1. Query Parser — extracts intent, entities, filters from natural language
  2. SQL Generator — generates Postgres SQL using Wren Engine or semantic prompt
  3. Results Formatter — turns SQL results into a human-readable insight

WHY 3 nodes and not 1?
Each node has a distinct job with distinct failure modes:
  - Parser fails → bad entity extraction, not a SQL syntax issue
  - SQL Gen fails → bad query, not a parsing issue
  - Formatter fails → display issue, not a data issue
Separating them makes debugging and testing each stage independently easy.
That said, for simple queries, one LLM call could do all three.
The split is justified when query complexity is high or when you want
to swap out the SQL layer (e.g., replace raw SQL with Wren Engine).

WREN ENGINE:
Wren Engine is a semantic SQL layer. Instead of writing raw SQL, you define
your data model in semantic terms ("revenue per region") and Wren generates
the optimized SQL. It also reduces token count because you send semantic
schema definitions instead of full table DDL.
In this implementation, we simulate Wren with a semantic prompt layer.
For real Wren integration, you'd call the Wren Engine API.
"""

import os
import json
import asyncio
import asyncpg
import logging
import base64
import wren
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# WREN ENGINE MANIFEST
#
# Real Modeling Definition Language (MDL) represented as a JSON manifest.
# Base64-encoded to initialize the offline WrenEngine.
# ─────────────────────────────────────────────
WREN_MANIFEST_DICT = {
  "catalog": "wren",
  "schema": "public",
  "models": [
    {
      "name": "products",
      "tableReference": {
        "schema": "public",
        "table": "products"
      },
      "columns": [
        { "name": "product_id", "type": "varchar" },
        { "name": "product_name", "type": "varchar" },
        { "name": "category", "type": "varchar" },
        { "name": "price", "type": "double" }
      ],
      "primaryKey": "product_id"
    },
    {
      "name": "supply_chain_records",
      "tableReference": {
        "schema": "public",
        "table": "supply_chain_records"
      },
      "columns": [
        { "name": "record_id", "type": "integer" },
        { "name": "product_id", "type": "varchar" },
        { "name": "supplier_id", "type": "varchar" },
        { "name": "order_quantity", "type": "integer" },
        { "name": "order_date", "type": "date" },
        { "name": "ship_date", "type": "date" },
        { "name": "delivery_date", "type": "date" },
        { "name": "shipping_costs", "type": "double" },
        { "name": "manufacturing_costs", "type": "double" },
        { "name": "revenue", "type": "double" },
        { "name": "region", "type": "varchar" },
        { "name": "customer_segment", "type": "varchar" }
      ],
      "primaryKey": "record_id"
    },
    {
      "name": "inventory",
      "tableReference": {
        "schema": "public",
        "table": "inventory"
      },
      "columns": [
        { "name": "id", "type": "integer" },
        { "name": "product_id", "type": "varchar" },
        { "name": "location", "type": "varchar" },
        { "name": "stock_level", "type": "integer" },
        { "name": "reorder_point", "type": "integer" },
        { "name": "max_capacity", "type": "integer" }
      ],
      "primaryKey": "id"
    },
    {
      "name": "forecast_metrics",
      "tableReference": {
        "schema": "public",
        "table": "forecast_metrics"
      },
      "columns": [
        { "name": "id", "type": "integer" },
        { "name": "product_id", "type": "varchar" },
        { "name": "run_date", "type": "date" },
        { "name": "model_name", "type": "varchar" },
        { "name": "mape", "type": "double" },
        { "name": "mae", "type": "double" },
        { "name": "notes", "type": "varchar" }
      ],
      "primaryKey": "id"
    }
  ],
  "relationships": [
    {
      "name": "records_to_products",
      "models": ["supply_chain_records", "products"],
      "joinType": "many_to_one",
      "condition": "supply_chain_records.product_id = products.product_id"
    },
    {
      "name": "inventory_to_products",
      "models": ["inventory", "products"],
      "joinType": "many_to_one",
      "condition": "inventory.product_id = products.product_id"
    },
    {
      "name": "forecast_to_products",
      "models": ["forecast_metrics", "products"],
      "joinType": "many_to_one",
      "condition": "forecast_metrics.product_id = products.product_id"
    }
  ]
}

WREN_MANIFEST_B64 = base64.b64encode(json.dumps(WREN_MANIFEST_DICT).encode('utf-8')).decode('utf-8')


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://scai:scai_password@localhost:5432/supply_chain")

# Use gpt-4o for SQL generation — it's better at structured output
sql_llm = ChatOpenAI(model="gpt-4o", temperature=0)
formatter_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

# ─────────────────────────────────────────────
# SEMANTIC SCHEMA (simulating Wren Engine)
#
# In a real Wren integration, this would be your data model definition
# sent to the Wren Engine API. Wren would return optimized SQL.
#
# HERE we simulate it: we give the LLM a semantic schema description
# instead of the raw DDL. This reduces token count significantly:
#   - Raw DDL: ~800 tokens (full CREATE TABLE statements)
#   - Semantic schema: ~200 tokens (just the meaningful fields)

# ─────────────────────────────────────────────
SEMANTIC_SCHEMA = """
Available data for supply chain analytics:

PRODUCTS (products):
  - product: product_id, product_name, category (skincare/haircare/cosmetics), price

TRANSACTIONS (supply_chain_records):
  - product: product_id
  - location: region (Northeast/Southeast/West/Midwest)
  - financials: revenue, shipping_costs, manufacturing_costs
  - quantities: order_quantity
  - dates: order_date, ship_date, delivery_date
  - segment: customer_segment (retail/wholesale)

INVENTORY (inventory):
  - product: product_id
  - location: location (same regions as above)
  - stock: stock_level, reorder_point, max_capacity
  - derived: status (CRITICAL when stock < reorder_point)

FORECASTING (forecast_metrics):
  - product: product_id
  - accuracy: mape (lower is better, >0.15 is high error)
  - model: model_name, hyperparameters (JSON)
  - when: run_date

RELATIONSHIPS:
  - supply_chain_records joins products via product_id
  - inventory joins products via product_id
  - forecast_metrics joins products via product_id

RULES:
  - Always include product_name in SELECT (not just product_id)
  - For stockout risk: WHERE stock_level < reorder_point
  - For MAPE analysis: ORDER BY mape DESC to find worst performers
  - Date format: 'YYYY-MM-DD'
  - Use Postgres syntax (not MySQL/SQLite)
"""


from typing import Optional

async def run_sql_insights(query: str, role: str, pool: Optional[asyncpg.Pool] = None) -> dict:
    """
    Run the full 3-node SQL insights pipeline.

    Args:
        query: Natural language question from the user
        role: User role (analyst/admin)
        pool: Optional asyncpg pool. If None, creates a temporary one.
              Pass the shared pool to avoid per-call connection churn.

    Returns:
        dict with 'sql_query', 'results', 'insight', 'token_count'
    """

    # ─────────────────────────────────────────────
    # NODE 1: QUERY PARSER
    # Extracts structured intent from the natural language query.
    # ─────────────────────────────────────────────
    parser_response = await sql_llm.ainvoke([
        SystemMessage(content="""Extract supply chain query intent as JSON.
Return ONLY a JSON object with:
{
  "query_type": "inventory|revenue|forecast|shipping|general",
  "filters": {"region": null|"Northeast"|"Southeast"|"West"|"Midwest",
               "category": null|"skincare"|"haircare"|"cosmetics",
               "time_period": null|"YYYY-MM-DD to YYYY-MM-DD"},
  "metrics": ["revenue", "stock_level", "mape", ...],
  "sort": "highest|lowest|null",
  "limit": 10
}"""),
        HumanMessage(content=query)
    ])

    try:
        parsed_intent = json.loads(parser_response.content)
    except json.JSONDecodeError:
        parsed_intent = {"query_type": "general", "filters": {}, "metrics": [], "sort": None, "limit": 10}

    logger.info(f"Parsed intent: {parsed_intent}")

    # ─────────────────────────────────────────────
    # NODE 2: SQL GENERATOR (with semantic schema / Wren simulation)
    #
    # WHY pass the semantic schema instead of raw DDL?
    # Token efficiency. The LLM only needs to know the meaningful fields,
    # not the full CREATE TABLE with constraints, defaults, and indexes.
    # In a real Wren integration, Wren itself generates the SQL from a
    # semantic model definition — you'd call wren_engine.query(intent).
    # ─────────────────────────────────────────────
    sql_response = await sql_llm.ainvoke([
        SystemMessage(content=f"""Generate a valid Postgres SQL query for supply chain analytics.
Use ONLY the schema described below. Return ONLY the SQL query, nothing else.

{SEMANTIC_SCHEMA}

Intent details: {json.dumps(parsed_intent)}"""),
        HumanMessage(content=query)
    ])

    sql_query = sql_response.content.strip()
    # Clean up markdown code fences if present
    if sql_query.startswith("```"):
        sql_query = sql_query.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    logger.info(f"Generated Semantic SQL: {sql_query[:200]}...")

    # ─────────────────────────────────────────────
    # WREN ENGINE COMPILATION
    # Compile the semantic SQL query using Wren Engine.
    # ─────────────────────────────────────────────
    try:
        engine = wren.WrenEngine(
            manifest_str=WREN_MANIFEST_B64,
            data_source="postgres",
            connection_info={}
        )
        compiled_query = engine.dry_plan(sql_query)
        logger.info(f"Wren Engine successfully compiled SQL query.")
        sql_query = compiled_query
    except Exception as e:
        logger.warning(f"Wren Engine compilation failed: {e}. Falling back to raw semantic query.")

    # ─────────────────────────────────────────────
    # EXECUTE THE SQL
    #
    # SAFETY: The LLM-generated SQL could contain destructive statements
    # (DROP TABLE, DELETE, etc.) if the model is confused or manipulated.
    # We defend in depth:
    #   1. Blocklist: reject known DDL/DML keywords before execution
    #   2. Read-only transaction: Postgres enforces no writes even if
    #      our blocklist misses something
    #   3. Timeout: kill long-running queries after 5 seconds
    # ─────────────────────────────────────────────
    import re

    BLOCKED_KEYWORDS = re.compile(
        r'\b(DROP|ALTER|TRUNCATE|DELETE|INSERT|UPDATE|CREATE|GRANT|REVOKE|COPY)\b',
        re.IGNORECASE,
    )

    results = []
    sql_error = None
    if BLOCKED_KEYWORDS.search(sql_query):
        sql_error = "Generated SQL contains forbidden DDL/DML statements — rejected for safety."
        logger.warning(f"SQL BLOCKED: {sql_query[:200]}")
    else:
        _pool_owner = False  # track whether we created the pool (and must close it)
        try:
            if pool is None:
                pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
                _pool_owner = True
            async with pool.acquire() as conn:
                # Set a 5-second statement timeout to prevent runaway queries
                await conn.execute("SET statement_timeout = '5s'")
                async with conn.transaction(readonly=True):
                    rows = await conn.fetch(sql_query)
                    results = [dict(row) for row in rows]
        except asyncpg.exceptions.ReadOnlySQLTransactionError:
            sql_error = "Query attempted to modify data — blocked by read-only transaction."
            logger.warning(f"SQL write attempt blocked: {sql_query[:200]}")
        except asyncio.TimeoutError:
            sql_error = "Query timed out after 5 seconds."
            logger.warning(f"SQL timeout: {sql_query[:200]}")
        except Exception as e:
            sql_error = f"SQL execution error: {str(e)}"
            logger.error(f"SQL execution error for query [{sql_query[:200]}]: {e}")
        finally:
            if _pool_owner and pool is not None:
                await pool.close()

    # ─────────────────────────────────────────────
    # NODE 3: RESULTS FORMATTER
    #
    # Turns raw SQL results into a natural language insight.
    # This is what the user sees in the chat UI.
    # ─────────────────────────────────────────────
    if sql_error:
        insight = f"Could not execute the query: {sql_error}"
    elif not results:
        insight = "No results found for that query. The data may not match your filters."
    else:
        formatter_response = await formatter_llm.ainvoke([
            SystemMessage(content="""You are a supply chain analyst. Summarize the SQL query results
in 2-4 clear, actionable sentences. Highlight the most important findings.
Mention specific numbers. Be concise — no bullet points, just prose."""),
            HumanMessage(content=f"Query: {query}\n\nResults: {json.dumps(results[:20], default=str)}")
        ])
        insight = formatter_response.content

    return {
        "sql_query": sql_query,
        "results": results,
        "insight": insight,
        "parsed_intent": parsed_intent,
        "result_count": len(results),
        "error": sql_error,
    }
