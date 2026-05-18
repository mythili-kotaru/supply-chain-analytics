"""
mcp_server/tools/inventory.py
────────────────────────────────
Inventory lookup tool implementation.
Straightforward SQL — the interesting part is how the Allocation Agent
uses this data to decide what to reorder.
"""

import asyncpg


async def inventory_lookup_impl(
    db_pool: asyncpg.Pool,
    product_id: str | None,
    location: str | None,
    below_reorder_only: bool
) -> list[dict]:

    conditions = []
    params = []
    param_idx = 1

    if product_id:
        conditions.append(f"i.product_id = ${param_idx}")
        params.append(product_id)
        param_idx += 1

    if location:
        conditions.append(f"i.location = ${param_idx}")
        params.append(location)
        param_idx += 1

    if below_reorder_only:
        conditions.append("i.stock_level < i.reorder_point")

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    sql = f"""
        SELECT
            i.product_id,
            p.product_name,
            p.category,
            i.location,
            i.stock_level,
            i.reorder_point,
            i.max_capacity,
            i.last_updated,
            -- Derived columns for quick analysis
            i.stock_level - i.reorder_point AS buffer_units,    -- negative = stockout risk
            ROUND(
                (i.stock_level::numeric / NULLIF(i.max_capacity, 0)) * 100, 1
            ) AS capacity_pct,
            CASE
                WHEN i.stock_level < i.reorder_point THEN 'CRITICAL'
                WHEN i.stock_level < i.reorder_point * 1.2 THEN 'LOW'
                ELSE 'OK'
            END AS status
        FROM inventory i
        JOIN products p ON i.product_id = p.product_id
        {where_clause}
        ORDER BY buffer_units ASC   -- most at-risk first
    """

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)

    return [
        {
            "product_id": row["product_id"],
            "product_name": row["product_name"],
            "category": row["category"],
            "location": row["location"],
            "stock_level": row["stock_level"],
            "reorder_point": row["reorder_point"],
            "max_capacity": row["max_capacity"],
            "buffer_units": row["buffer_units"],
            "capacity_pct": float(row["capacity_pct"]) if row["capacity_pct"] else None,
            "status": row["status"],
            "last_updated": str(row["last_updated"])
        }
        for row in rows
    ]
