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
import time
import tiktoken
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
# WREN SEMANTIC & DDL SCHEMAS
#
# Real Wren integration utilizes the structured JSON manifest (MDL)
# to dynamically construct a concise prompt context.
#
# We compare this against the traditional Raw DDL schema approach
# to measure the exact token reduction and compile validity.
# ─────────────────────────────────────────────

def get_wren_schema_prompt(manifest: dict) -> str:
    lines = ["Wren Semantic Model Schema:"]
    for model in manifest.get("models", []):
        model_name = model.get("name")
        table_name = model.get("tableReference", {}).get("table")
        lines.append(f"\nModel: {model_name} (maps to table: {table_name})")
        cols = []
        for col in model.get("columns", []):
            cols.append(f"{col.get('name')} ({col.get('type')})")
        lines.append(f"  Columns: {', '.join(cols)}")
        if model.get("primaryKey"):
            lines.append(f"  Primary Key: {model.get('primaryKey')}")
            
    if manifest.get("relationships"):
        lines.append("\nRelationships:")
        for rel in manifest.get("relationships", []):
            lines.append(f"  - {rel.get('name')}: {rel.get('models')[0]} joins {rel.get('models')[1]} ON {rel.get('condition')}")
            
    lines.append("""
Rules:
  - Always include product_name in SELECT (not just product_id)
  - For stockout risk: WHERE stock_level < reorder_point
  - For MAPE analysis: ORDER BY mape DESC to find worst performers
  - Note that MAPE is stored as a decimal fraction in the database (e.g. 0.20 represents 20%). If the query asks for a percentage value like '20%', use the decimal equivalent '0.20' in the SQL.
  - Date format: 'YYYY-MM-DD'
  - Use Postgres syntax
""")
    return "\n".join(lines)


RAW_DDL_SCHEMA = """
PostgreSQL Database Schema (DDL):

CREATE TABLE products (
    product_id      TEXT PRIMARY KEY,
    product_name    TEXT NOT NULL,
    category        TEXT NOT NULL,
    price           NUMERIC(10, 2),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE suppliers (
    supplier_id     TEXT PRIMARY KEY,
    supplier_name   TEXT NOT NULL,
    location        TEXT,
    lead_time_days  INTEGER,
    defect_rate     NUMERIC(5, 4)
);

CREATE TABLE inventory (
    id              SERIAL PRIMARY KEY,
    product_id      TEXT REFERENCES products(product_id),
    location        TEXT NOT NULL,
    stock_level     INTEGER NOT NULL,
    reorder_point   INTEGER NOT NULL,
    max_capacity    INTEGER NOT NULL,
    last_updated    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE supply_chain_records (
    record_id           SERIAL PRIMARY KEY,
    product_id          TEXT REFERENCES products(product_id),
    supplier_id         TEXT REFERENCES suppliers(supplier_id),
    order_quantity      INTEGER,
    order_date          DATE,
    ship_date           DATE,
    delivery_date       DATE,
    shipping_costs      NUMERIC(10, 2),
    manufacturing_costs NUMERIC(10, 2),
    revenue             NUMERIC(10, 2),
    region              TEXT,
    customer_segment    TEXT,
    embedding           vector(1536),
    search_vector       tsvector
);

CREATE TABLE forecast_metrics (
    id              SERIAL PRIMARY KEY,
    product_id      TEXT REFERENCES products(product_id),
    run_date        DATE NOT NULL,
    model_name      TEXT NOT NULL,
    mape            NUMERIC(6, 4),
    mae             NUMERIC(10, 2),
    hyperparameters JSONB,
    notes           TEXT
);

CREATE TABLE hyperparameter_tuning_log (
    id              SERIAL PRIMARY KEY,
    product_id      TEXT REFERENCES products(product_id),
    agent_run_id    TEXT,
    proposed_at     TIMESTAMPTZ DEFAULT NOW(),
    old_params      JSONB,
    new_params      JSONB,
    rationale       TEXT,
    status          TEXT DEFAULT 'proposed'
);

Rules:
  - Always join supply_chain_records/inventory/forecast_metrics with products using product_id to get product_name
  - Always include product_name in SELECT (not just product_id)
  - For stockout risk: WHERE stock_level < reorder_point
  - For MAPE analysis: ORDER BY mape DESC to find worst performers
  - Note that MAPE is stored as a decimal fraction in the database (e.g. 0.20 represents 20%). If the query asks for a percentage value like '20%', use the decimal equivalent '0.20' in the SQL.
  - Date format: 'YYYY-MM-DD'
  - Use Postgres syntax
"""

def count_tokens(text: str, model: str = "gpt-4o") -> int:
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except Exception:
        return len(text.split())

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
    # NODE 2: SQL GENERATION (Wren Manifest vs Raw DDL Comparison)
    #
    # We run both generation prompts concurrently to compare performance metrics,
    # token count reductions, and compiled query outcomes.
    # ─────────────────────────────────────────────
    wren_schema = get_wren_schema_prompt(WREN_MANIFEST_DICT)

    async def run_wren_path():
        start_time = time.time()
        wren_prompt_tokens = count_tokens(wren_schema) + count_tokens(query) + 100
        wren_resp = await sql_llm.ainvoke([
            SystemMessage(content=f"""Generate a valid Postgres SQL query for supply chain analytics.
Use ONLY the schema described below. Return ONLY the SQL query, nothing else.

{wren_schema}

Intent details: {json.dumps(parsed_intent)}"""),
            HumanMessage(content=query)
        ])
        latency = (time.time() - start_time) * 1000
        wren_sql = wren_resp.content.strip()
        if wren_sql.startswith("```"):
            wren_sql = wren_sql.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        
        wren_compiled = False
        compiled_query = wren_sql
        try:
            engine = wren.WrenEngine(
                manifest_str=WREN_MANIFEST_B64,
                data_source="postgres",
                connection_info={}
            )
            compiled_query = engine.dry_plan(wren_sql)
            wren_compiled = True
        except Exception as e:
            logger.warning(f"Wren Engine compilation failed: {e}")
            
        return {
            "mode": "wren",
            "prompt_tokens": wren_prompt_tokens,
            "completion_tokens": count_tokens(wren_sql),
            "total_tokens": wren_prompt_tokens + count_tokens(wren_sql),
            "latency_ms": latency,
            "sql_generated": wren_sql,
            "sql_compiled": compiled_query,
            "wren_compiled": wren_compiled
        }

    async def run_ddl_path():
        start_time = time.time()
        ddl_prompt_tokens = count_tokens(RAW_DDL_SCHEMA) + count_tokens(query) + 100
        ddl_resp = await sql_llm.ainvoke([
            SystemMessage(content=f"""Generate a valid Postgres SQL query for supply chain analytics.
Use ONLY the schema described below. Return ONLY the SQL query, nothing else.

{RAW_DDL_SCHEMA}

Intent details: {json.dumps(parsed_intent)}"""),
            HumanMessage(content=query)
        ])
        latency = (time.time() - start_time) * 1000
        ddl_sql = ddl_resp.content.strip()
        if ddl_sql.startswith("```"):
            ddl_sql = ddl_sql.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            
        ddl_compiled = False
        try:
            engine = wren.WrenEngine(
                manifest_str=WREN_MANIFEST_B64,
                data_source="postgres",
                connection_info={}
            )
            engine.dry_plan(ddl_sql)
            ddl_compiled = True
        except Exception:
            pass
            
        return {
            "mode": "ddl",
            "prompt_tokens": ddl_prompt_tokens,
            "completion_tokens": count_tokens(ddl_sql),
            "total_tokens": ddl_prompt_tokens + count_tokens(ddl_sql),
            "latency_ms": latency,
            "sql_generated": ddl_sql,
            "sql_compiled": ddl_sql,
            "wren_compiled": ddl_compiled
        }

    wren_stats, ddl_stats = await asyncio.gather(run_wren_path(), run_ddl_path())
    
    sql_query = wren_stats["sql_compiled"]
    token_saving_pct = ((ddl_stats["prompt_tokens"] - wren_stats["prompt_tokens"]) / ddl_stats["prompt_tokens"]) * 100
    
    logger.info(f"Wren path compiled: {wren_stats['wren_compiled']}. Saved {token_saving_pct:.1f}% prompt tokens.")

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
        "wren_stats": wren_stats,
        "ddl_stats": ddl_stats,
        "token_saving_pct": round(token_saving_pct, 2),
    }
