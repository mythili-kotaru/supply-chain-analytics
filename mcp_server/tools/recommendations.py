"""
mcp_server/tools/recommendations.py
──────────────────────────────────────
Submit a hyperparameter tuning recommendation.
Admin-only write operation — called by the Forecasting Analyst agent
after human approval via LangGraph interrupt().
"""

import asyncpg
import json


async def submit_recommendation_impl(
    db_pool: asyncpg.Pool,
    product_id: str,
    old_params: dict,
    new_params: dict,
    rationale: str,
    agent_run_id: str
) -> dict:

    sql = """
        INSERT INTO hyperparameter_tuning_log
            (product_id, agent_run_id, old_params, new_params, rationale, status)
        VALUES ($1, $2, $3, $4, $5, 'proposed')
        RETURNING id, proposed_at
    """

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            sql,
            product_id,
            agent_run_id,
            json.dumps(old_params),
            json.dumps(new_params),
            rationale
        )

    return {
        "log_id": row["id"],
        "proposed_at": str(row["proposed_at"]),
        "status": "proposed",
        "message": f"Recommendation logged for {product_id}. Awaiting approval."
    }
