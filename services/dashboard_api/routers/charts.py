"""
GET /charts/inventory-health
Returns CRITICAL/LOW/OK counts grouped by product category.
Powers the Inventory Health Donut chart on the dashboard.

GET /charts/po-value-by-category
Returns total approved PO value grouped by product category.
Powers the PO Value Bar chart on the dashboard.
"""
from fastapi import APIRouter, Depends
import asyncpg
from database import get_db

router = APIRouter()


@router.get("/charts/inventory-health")
async def get_inventory_health_chart(db: asyncpg.Pool = Depends(get_db)):
    """
    Returns counts for CRITICAL, LOW, and OK inventory items across all products.
    Used to power the donut chart on the main dashboard.
    """
    rows = await db.fetch("""
        SELECT
            CASE
                WHEN i.stock_level <= i.reorder_point * 0.5 THEN 'CRITICAL'
                WHEN i.stock_level <= i.reorder_point       THEN 'LOW'
                ELSE 'OK'
            END AS status,
            COUNT(*) AS count
        FROM inventory i
        GROUP BY status
        ORDER BY status
    """)
    return {row["status"]: row["count"] for row in rows}


@router.get("/charts/inventory-by-category")
async def get_inventory_by_category_chart(db: asyncpg.Pool = Depends(get_db)):
    """
    Returns average capacity_pct per category.
    Used to power the category breakdown bar chart on the main dashboard.
    """
    rows = await db.fetch("""
        SELECT
            p.category,
            ROUND(AVG(
                (i.stock_level::numeric / NULLIF(i.max_capacity, 0)) * 100
            ), 1) AS avg_capacity_pct,
            COUNT(*) AS sku_count,
            SUM(CASE WHEN i.stock_level <= i.reorder_point THEN 1 ELSE 0 END) AS at_risk
        FROM inventory i
        JOIN products p ON p.product_id = i.product_id
        GROUP BY p.category
        ORDER BY p.category
    """)
    return [
        {
            "category": row["category"],
            "avg_capacity_pct": float(row["avg_capacity_pct"]),
            "sku_count": row["sku_count"],
            "at_risk": row["at_risk"],
        }
        for row in rows
    ]
