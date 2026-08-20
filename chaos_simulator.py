import os
import asyncio
import random
import logging
import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from notifier import send_alert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("chaos_simulator")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://scai:scai_password@localhost:5432/supply_chain")

async def inject_demand_shock():
    """
    Randomly drops inventory levels for a random product to simulate an unexpected spike in demand.
    This will force the AI agents to react and create replenishment/allocation proposals.
    """
    logger.info("Chaos Monkey: Attempting to inject a demand shock...")
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
        async with pool.acquire() as conn:
            # Pick a random product from inventory that isn't already critical
            rows = await conn.fetch("SELECT id, product_id, stock_level, reorder_point FROM inventory WHERE stock_level > reorder_point")
            
            if rows:
                target = random.choice(rows)
                # Drop stock to just below the reorder point
                new_stock = max(0, target['reorder_point'] - random.randint(1, 50))
                
                await conn.execute("UPDATE inventory SET stock_level = $1 WHERE id = $2", new_stock, target['id'])
                msg = f"Chaos Monkey Strike! 🌪️ Dropped stock for {target['product_id']} from {target['stock_level']} to {new_stock} (below reorder point {target['reorder_point']})"
                logger.warning(msg)
                send_alert(msg)
            else:
                logger.info("Chaos Monkey: All items are already critical or below reorder point. No shock injected.")
                
        await pool.close()
    except Exception as e:
        logger.error(f"Error injecting demand shock: {e}", exc_info=True)

async def inject_supplier_delay():
    """
    Randomly increases the lead time for a supplier to simulate logistics delays.
    """
    logger.info("Chaos Monkey: Attempting to inject a supplier delay...")
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT supplier_id, supplier_name, lead_time_days FROM suppliers")
            
            if rows:
                target = random.choice(rows)
                delay_days = random.randint(2, 7)
                new_lead_time = target['lead_time_days'] + delay_days
                
                await conn.execute("UPDATE suppliers SET lead_time_days = $1 WHERE supplier_id = $2", new_lead_time, target['supplier_id'])
                msg = f"Chaos Monkey Strike! 🌪️ Delayed supplier {target['supplier_name']} by {delay_days} days. New lead time: {new_lead_time} days."
                logger.warning(msg)
                send_alert(msg)
            
        await pool.close()
    except Exception as e:
        logger.error(f"Error injecting supplier delay: {e}", exc_info=True)

async def inject_quality_issue():
    """
    Randomly degrades the quality/defect_rate of a supplier to simulate
    a quality control failure. This should trigger supplier evaluation
    and sourcing agents to react.
    """
    logger.info("Chaos Monkey: Attempting to inject a supplier quality issue...")
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
        async with pool.acquire() as conn:
            # Pick a supplier with a currently acceptable defect rate
            rows = await conn.fetch("SELECT supplier_id, supplier_name, defect_rate FROM suppliers WHERE defect_rate < 0.10")
            
            if rows:
                target = random.choice(rows)
                # Spike defect rate by 5-20 percentage points
                spike = round(random.uniform(0.05, 0.20), 3)
                new_defect_rate = min(1.0, round(target['defect_rate'] + spike, 3))
                
                await conn.execute("UPDATE suppliers SET defect_rate = $1 WHERE supplier_id = $2", new_defect_rate, target['supplier_id'])
                msg = (
                    f"Chaos Monkey Strike! 🌪️ Quality degradation at {target['supplier_name']} — "
                    f"defect rate jumped from {target['defect_rate']*100:.1f}% to {new_defect_rate*100:.1f}%."
                )
                logger.warning(msg)
                send_alert(msg)
            else:
                logger.info("Chaos Monkey: No suppliers with acceptable defect rates to degrade. Skipping.")

        await pool.close()
    except Exception as e:
        logger.error(f"Error injecting quality issue: {e}", exc_info=True)

async def inject_capacity_reduction():
    """
    Randomly reduces the max_capacity of an inventory location to simulate
    a warehouse incident or machine breakdown, forcing allocation agents
    to re-route stock.
    """
    logger.info("Chaos Monkey: Attempting to inject a capacity reduction...")
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
        async with pool.acquire() as conn:
            # Get distinct warehouse locations with high capacity
            rows = await conn.fetch("""
                SELECT DISTINCT location, MAX(max_capacity) as max_cap
                FROM inventory
                GROUP BY location
                HAVING MAX(max_capacity) > 200
            """)

            if rows:
                target = random.choice(rows)
                location = target['location']
                # Reduce max_capacity by 20-40%
                reduction_pct = round(random.uniform(0.20, 0.40), 2)
                new_capacity = max(50, int(target['max_cap'] * (1 - reduction_pct)))

                await conn.execute(
                    "UPDATE inventory SET max_capacity = $1 WHERE location = $2",
                    new_capacity, location
                )
                msg = (
                    f"Chaos Monkey Strike! 🌪️ Capacity crunch at {location} — "
                    f"max capacity reduced by {int(reduction_pct*100)}% to {new_capacity} units. "
                    f"Simulating warehouse incident."
                )
                logger.warning(msg)
                send_alert(msg)
            else:
                logger.info("Chaos Monkey: No high-capacity locations found. Skipping capacity reduction.")

        await pool.close()
    except Exception as e:
        logger.error(f"Error injecting capacity reduction: {e}", exc_info=True)

if __name__ == "__main__":
    logger.info("Starting Supply Chain AI Chaos Simulator...")
    send_alert("⚠️ *Chaos Simulator is online and active. Prepare for automated disruptions.*")
    scheduler = AsyncIOScheduler()
    
    # Inject a demand shock randomly every 1 to 4 hours
    scheduler.add_job(inject_demand_shock, 'interval', hours=2, jitter=3600, id='demand_shock')
    
    # Inject a supplier delay randomly every 12 to 24 hours
    scheduler.add_job(inject_supplier_delay, 'interval', hours=18, jitter=21600, id='supplier_delay')
    
    # Inject a supplier quality issue randomly every 6 to 12 hours
    scheduler.add_job(inject_quality_issue, 'interval', hours=9, jitter=10800, id='quality_issue')
    
    # Inject a warehouse capacity reduction randomly every 8 to 16 hours
    scheduler.add_job(inject_capacity_reduction, 'interval', hours=12, jitter=14400, id='capacity_reduction')
    
    scheduler.start()
    
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
