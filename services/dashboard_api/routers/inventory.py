"""
GET /inventory/alerts

Returns all inventory rows that are CRITICAL or LOW (below reorder point),
joined with product metadata. Ordered by buffer_units ASC so the most
at-risk SKUs appear at the top of the dashboard feed.

Why denormalize status here instead of storing it?
Status is derived: it depends on current stock_level vs reorder_point.
Computing it at query time means we never have stale status from a
previous snapshot — the dashboard always reflects live Postgres state.
"""
from fastapi import APIRouter, Depends
import asyncpg
from database import get_db
from models import InventoryAlert

router = APIRouter()


@router.get("/inventory/alerts", response_model=list[InventoryAlert])
async def get_inventory_alerts(db: asyncpg.Pool = Depends(get_db)):
    rows = await db.fetch("""
        SELECT
            i.product_id,
            p.product_name,
            p.category,
            i.location,
            i.stock_level,
            i.reorder_point,
            i.max_capacity,
            ROUND(
                (i.stock_level::numeric / NULLIF(i.max_capacity, 0)) * 100,
                1
            )                                               AS capacity_pct,
            CASE
                WHEN i.stock_level <= i.reorder_point * 0.5 THEN 'CRITICAL'
                WHEN i.stock_level <= i.reorder_point       THEN 'LOW'
                ELSE 'OK'
            END                                             AS status,
            i.last_updated::text                            AS last_updated,
            -- used for ordering only, not returned
            i.reorder_point - i.stock_level                AS buffer_units
        FROM inventory i
        JOIN products p ON p.product_id = i.product_id
        WHERE i.stock_level <= i.reorder_point
        ORDER BY buffer_units DESC
    """)

    return [
        InventoryAlert(
            product_id=row["product_id"],
            product_name=row["product_name"],
            category=row["category"],
            location=row["location"],
            stock_level=row["stock_level"],
            reorder_point=row["reorder_point"],
            max_capacity=row["max_capacity"],
            capacity_pct=float(row["capacity_pct"] or 0),
            status=row["status"],
            last_updated=row["last_updated"],
        )
        for row in rows
    ]


@router.get("/inventory/all", response_model=list[InventoryAlert])
async def get_inventory_all(db: asyncpg.Pool = Depends(get_db)):
    """
    Returns ALL inventory rows, computing the live status and capacity_pct.
    Used for the main Inventory tab data grid.
    """
    rows = await db.fetch("""
        SELECT
            i.product_id,
            p.product_name,
            p.category,
            i.location,
            i.stock_level,
            i.reorder_point,
            i.max_capacity,
            ROUND(
                (i.stock_level::numeric / NULLIF(i.max_capacity, 0)) * 100,
                1
            )                                               AS capacity_pct,
            CASE
                WHEN i.stock_level <= i.reorder_point * 0.5 THEN 'CRITICAL'
                WHEN i.stock_level <= i.reorder_point       THEN 'LOW'
                ELSE 'OK'
            END                                             AS status,
            i.last_updated::text                            AS last_updated
        FROM inventory i
        JOIN products p ON p.product_id = i.product_id
        ORDER BY status ASC, capacity_pct ASC
    """)

    return [
        InventoryAlert(
            product_id=row["product_id"],
            product_name=row["product_name"],
            category=row["category"],
            location=row["location"],
            stock_level=row["stock_level"],
            reorder_point=row["reorder_point"],
            max_capacity=row["max_capacity"],
            capacity_pct=float(row["capacity_pct"] or 0),
            status=row["status"],
            last_updated=row["last_updated"],
        )
        for row in rows
    ]

@router.get("/inventory/critical", response_model=list[InventoryAlert])
async def get_inventory_critical(db: asyncpg.Pool = Depends(get_db)):
    """
    Returns only CRITICAL inventory rows (stock level <= 50% of reorder point).
    Used for the immediate attention widget on the dashboard.
    """
    rows = await db.fetch("""
        SELECT
            i.product_id,
            p.product_name,
            p.category,
            i.location,
            i.stock_level,
            i.reorder_point,
            i.max_capacity,
            ROUND(
                (i.stock_level::numeric / NULLIF(i.max_capacity, 0)) * 100,
                1
            )                                               AS capacity_pct,
            'CRITICAL'                                      AS status,
            i.last_updated::text                            AS last_updated,
            i.reorder_point - i.stock_level                AS buffer_units
        FROM inventory i
        JOIN products p ON p.product_id = i.product_id
        WHERE i.stock_level <= i.reorder_point * 0.5
        ORDER BY buffer_units DESC
    """)

    return [
        InventoryAlert(
            product_id=row["product_id"],
            product_name=row["product_name"],
            category=row["category"],
            location=row["location"],
            stock_level=row["stock_level"],
            reorder_point=row["reorder_point"],
            max_capacity=row["max_capacity"],
            capacity_pct=float(row["capacity_pct"] or 0),
            status=row["status"],
            last_updated=row["last_updated"],
        )
        for row in rows
    ]
