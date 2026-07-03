import os
import asyncio
import random
import logging
import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler

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
                logger.warning(f"Chaos Monkey Strike! 🌪️ Dropped stock for {target['product_id']} from {target['stock_level']} to {new_stock} (below reorder point {target['reorder_point']})")
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
                logger.warning(f"Chaos Monkey Strike! 🌪️ Delayed supplier {target['supplier_name']} by {delay_days} days. New lead time: {new_lead_time} days.")
            
        await pool.close()
    except Exception as e:
        logger.error(f"Error injecting supplier delay: {e}", exc_info=True)

if __name__ == "__main__":
    logger.info("Starting Supply Chain AI Chaos Simulator...")
    scheduler = AsyncIOScheduler()
    
    # Inject a demand shock randomly every 1 to 4 hours
    scheduler.add_job(inject_demand_shock, 'interval', hours=2, jitter=3600, id='demand_shock')
    
    # Inject a supplier delay randomly every 12 to 24 hours
    scheduler.add_job(inject_supplier_delay, 'interval', hours=18, jitter=21600, id='supplier_delay')
    
    scheduler.start()
    
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
