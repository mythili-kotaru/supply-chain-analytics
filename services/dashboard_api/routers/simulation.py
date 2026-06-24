import logging
import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import asyncpg

from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Pydantic Request/Response Models ─────────────────────────────────────────

class SimulationRequest(BaseModel):
    demand_multiplier: float = 1.0
    lead_time_multiplier: float = 1.0
    disrupted_supplier_id: Optional[str] = None

class SimulationSummary(BaseModel):
    base_lost_revenue: float
    simulated_lost_revenue: float
    revenue_impact: float
    base_stockouts: int
    simulated_stockouts: int

class TimelinePoint(BaseModel):
    day: int
    base_stock: float
    simulated_stock: float

class ChartData(BaseModel):
    product_id: str
    product_name: str
    location: str
    timeline: List[TimelinePoint]

class StockoutDetail(BaseModel):
    product_id: str
    product_name: str
    location: str
    base_days_to_stockout: int  # 31 if no stockout
    simulated_days_to_stockout: int
    base_lost_revenue: float
    simulated_lost_revenue: float

class MitigationAction(BaseModel):
    product_id: str
    product_name: str
    location: str
    action_type: str  # "transfer" or "purchase_order"
    details: str
    quantity: int
    source_location: Optional[str] = None
    supplier_name: Optional[str] = None

class SimulationResponse(BaseModel):
    summary: SimulationSummary
    charts: List[ChartData]
    stockout_details: List[StockoutDetail]
    mitigations: List[MitigationAction]


# ── Simulation Logic ─────────────────────────────────────────────────────────

@router.post("/simulation/run", response_model=SimulationResponse)
async def run_simulation(req: SimulationRequest, db: asyncpg.Pool = Depends(get_db)):
    """
    Day 11: What-If Demand Simulation & Scenario Sandbox Engine.
    Runs a 30-day forward daily inventory projection under:
      - Base Scenario (1.0x demand, 1.0x lead times, no outages)
      - Simulated Scenario (user-defined demand spike, lead time scaling, supplier outage)
    Generates projected stock charts, alerts, and mitigation actions.
    """
    try:
        # 1. Fetch inventory, products and supplier details
        query_inventory = """
            WITH product_supplier AS (
                SELECT DISTINCT ON (product_id) 
                    product_id, 
                    supplier_id
                FROM supply_chain_records
                GROUP BY product_id, supplier_id, record_id
                ORDER BY product_id, COUNT(*) OVER(PARTITION BY product_id, supplier_id) DESC
            )
            SELECT 
                i.product_id,
                p.product_name,
                p.category,
                COALESCE(p.price, 15.00) AS price,
                i.location,
                i.stock_level,
                i.reorder_point,
                i.max_capacity,
                s.supplier_id,
                s.supplier_name,
                COALESCE(s.lead_time_days, 10) AS base_lead_time
            FROM inventory i
            JOIN products p ON p.product_id = i.product_id
            LEFT JOIN product_supplier ps ON ps.product_id = i.product_id
            LEFT JOIN suppliers s ON s.supplier_id = ps.supplier_id
        """
        inv_rows = await db.fetch(query_inventory)

        # 2. Fetch historical sales to calculate daily sales velocity per product+region
        query_velocity = """
            SELECT product_id, region, COUNT(*) as record_count, SUM(order_quantity) as total_qty
            FROM supply_chain_records
            GROUP BY product_id, region
        """
        vel_rows = await db.fetch(query_velocity)

        # Map velocity
        velocity_map = {}
        for row in vel_rows:
            # We assume each historical order represents roughly a 30-day supply cycle.
            # So average daily demand = total_qty / (record_count * 30 days)
            count = row["record_count"] or 1
            total_qty = row["total_qty"] or 300
            velocity_map[(row["product_id"], row["region"])] = float(total_qty) / (count * 30.0)

        # Build items list
        items = []
        for row in inv_rows:
            pid = row["product_id"]
            loc = row["location"]
            reorder = row["reorder_point"]
            
            # Fallback velocity if not in historical records: reorder_point / 30
            fallback_vel = max(1.0, float(reorder) / 30.0)
            base_vel = velocity_map.get((pid, loc), fallback_vel)

            items.append({
                "product_id": pid,
                "product_name": row["product_name"],
                "category": row["category"],
                "price": float(row["price"]),
                "location": loc,
                "stock_level": row["stock_level"],
                "reorder_point": reorder,
                "max_capacity": row["max_capacity"],
                "supplier_id": row["supplier_id"],
                "supplier_name": row["supplier_name"],
                "base_lead_time": row["base_lead_time"],
                "base_daily_demand": base_vel
            })

        # 3. Helper function to project a single item over 30 days
        def project_item(item: dict, demand_mult: float, lead_mult: float, outage_sup_id: Optional[str]) -> tuple:
            # Setup initial state
            stock = float(item["stock_level"])
            max_cap = float(item["max_capacity"])
            reorder = float(item["reorder_point"])
            price = item["price"]
            daily_demand = item["base_daily_demand"] * demand_mult

            # Supplier lead time math
            sup_id = item["supplier_id"]
            base_lead = item["base_lead_time"]
            
            if outage_sup_id and sup_id == outage_sup_id:
                # Disrupted supplier: shipments never arrive
                lead_time = 999999
            else:
                lead_time = int(base_lead * lead_mult)

            pending_arrivals = [] # list of (arrival_day, quantity)
            order_in_transit = False
            lost_revenue = 0.0
            days_to_stockout = 31 # default to no stockout
            timeline = []

            for d in range(1, 31):
                # Apply arrivals
                arrived_qty = 0
                for arr_day, qty in list(pending_arrivals):
                    if arr_day == d:
                        arrived_qty += qty
                        pending_arrivals.remove((arr_day, qty))
                        order_in_transit = False

                stock = min(max_cap, stock + arrived_qty)

                # Process demand
                if stock <= 0:
                    lost_revenue += daily_demand * price
                    stock = 0.0
                    days_to_stockout = min(days_to_stockout, d)
                else:
                    if stock - daily_demand <= 0:
                        unfulfilled = daily_demand - stock
                        lost_revenue += unfulfilled * price
                        stock = 0.0
                        days_to_stockout = min(days_to_stockout, d)
                    else:
                        stock -= daily_demand

                # Record day end stock
                timeline.append((d, stock))

                # Trigger replenishment order if needed
                if stock <= reorder and not order_in_transit:
                    order_qty = max_cap - stock
                    pending_arrivals.append((d + lead_time, order_qty))
                    order_in_transit = True

            return timeline, days_to_stockout, lost_revenue, stock

        # 4. Run simulations for base & simulated scenarios
        charts = []
        stockout_details = []
        simulated_results = {} # store simulated ending stock for mitigation analysis

        base_total_lost_rev = 0.0
        sim_total_lost_rev = 0.0
        base_stockout_count = 0
        sim_stockout_count = 0

        for item in items:
            pid = item["product_id"]
            loc = item["location"]
            name = item["product_name"]

            # Base scenario
            base_timeline, base_days, base_lost, base_end_stock = project_item(item, 1.0, 1.0, None)
            
            # Simulated scenario
            sim_timeline, sim_days, sim_lost, sim_end_stock = project_item(
                item, 
                req.demand_multiplier, 
                req.lead_time_multiplier, 
                req.disrupted_supplier_id
            )

            # Accumulate totals
            base_total_lost_rev += base_lost
            sim_total_lost_rev += sim_lost
            if base_days <= 30:
                base_stockout_count += 1
            if sim_days <= 30:
                sim_stockout_count += 1

            # Store simulated end stock for transfer analysis
            simulated_results[(pid, loc)] = {
                "end_stock": sim_end_stock,
                "days_to_stockout": sim_days,
                "item": item
            }

            # Map timeline points
            points = []
            for i in range(30):
                points.append(TimelinePoint(
                    day=base_timeline[i][0],
                    base_stock=round(base_timeline[i][1], 1),
                    simulated_stock=round(sim_timeline[i][1], 1)
                ))

            charts.append(ChartData(
                product_id=pid,
                product_name=name,
                location=loc,
                timeline=points
            ))

            stockout_details.append(StockoutDetail(
                product_id=pid,
                product_name=name,
                location=loc,
                base_days_to_stockout=base_days,
                simulated_days_to_stockout=sim_days,
                base_lost_revenue=round(base_lost, 2),
                simulated_lost_revenue=round(sim_lost, 2)
            ))

        # 5. Generate AI mitigations for products experiencing simulated stockouts
        mitigations = []
        for (pid, loc), res in simulated_results.items():
            sim_days = res["days_to_stockout"]
            item = res["item"]

            if sim_days <= 30:
                # This location is stocking out! Let's check for surplus locations of the same product
                surplus_source = None
                max_surplus = 0.0

                for (other_pid, other_loc), other_res in simulated_results.items():
                    if other_pid == pid and other_loc != loc:
                        other_stock = other_res["end_stock"]
                        other_reorder = other_res["item"]["reorder_point"]
                        # Location has surplus if ending stock is 20% above safety stock
                        if other_stock > other_reorder * 1.2:
                            surplus_qty = other_stock - other_reorder
                            if surplus_qty > max_surplus:
                                max_surplus = surplus_qty
                                surplus_source = other_loc

                if surplus_source:
                    # Suggest transfer
                    transfer_qty = int(min(item["max_capacity"] - item["stock_level"], max_surplus))
                    if transfer_qty > 0:
                        mitigations.append(MitigationAction(
                            product_id=pid,
                            product_name=item["product_name"],
                            location=loc,
                            action_type="transfer",
                            details=f"Transfer {transfer_qty} units from {surplus_source} region (estimated delivery 2-3 days).",
                            quantity=transfer_qty,
                            source_location=surplus_source
                        ))
                else:
                    # Suggest Purchase Order
                    po_qty = int(item["max_capacity"] - item["stock_level"])
                    mitigations.append(MitigationAction(
                        product_id=pid,
                        product_name=item["product_name"],
                        location=loc,
                        action_type="purchase_order",
                        details=f"Place urgent replenishment order for {po_qty} units with {item['supplier_name'] or 'primary supplier'}.",
                        quantity=po_qty,
                        supplier_name=item["supplier_name"] or "Primary Supplier"
                    ))

        # 6. Formulate summary
        summary = SimulationSummary(
            base_lost_revenue=round(base_total_lost_rev, 2),
            simulated_lost_revenue=round(sim_total_lost_rev, 2),
            revenue_impact=round(sim_total_lost_rev - base_total_lost_rev, 2),
            base_stockouts=base_stockout_count,
            simulated_stockouts=sim_stockout_count
        )

        return SimulationResponse(
            summary=summary,
            charts=charts,
            stockout_details=stockout_details,
            mitigations=mitigations
        )

    except Exception as e:
        logger.exception("Error running scenario simulation")
        raise HTTPException(status_code=500, detail=f"Simulation failed: {str(e)}")
