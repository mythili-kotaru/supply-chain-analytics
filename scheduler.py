import os
import asyncio
import logging
import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from agents.supervisor import run_supervisor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("scheduler")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://scai:scai_password@localhost:5432/supply_chain")

async def check_inventory_violations():
    logger.info("Scanning inventory for violations...")
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
        async with pool.acquire() as conn:
            # Find products with critical stock or below reorder point
            rows = await conn.fetch("""
                SELECT product_id, stock_level, reorder_point, location 
                FROM inventory 
                WHERE stock_level < reorder_point OR stock_level <= 0
            """)
            
            for row in rows:
                product_id = row['product_id']
                
                # Check if there is already a pending allocation task for this product
                pending_task = await conn.fetchval("""
                    SELECT 1 FROM allocation_tasks 
                    WHERE product_id = $1 AND status = 'pending' LIMIT 1
                """, product_id)
                
                if pending_task:
                    logger.info(f"Skipping inventory violation for {product_id} as a task is already pending.")
                    continue

                logger.warning(f"Inventory violation detected for {product_id} at {row['location']} (Stock: {row['stock_level']}, Reorder: {row['reorder_point']})")
                
                # Trigger supervisor
                query = f"The stock for {product_id} is critically low. Please allocate or replenish it."
                logger.info(f"Triggering supervisor for {product_id}: {query}")
                
                # We iterate through the stream to ensure it runs to completion (up to HITL interrupt)
                async for event in run_supervisor(user_query=query, user_role="admin"):
                    pass 
                
                logger.info(f"Supervisor successfully triggered and paused at HITL for {product_id}.")
                
        await pool.close()
    except Exception as e:
        logger.error(f"Error checking inventory: {e}", exc_info=True)

async def check_mape_violations():
    logger.info("Scanning forecast metrics for MAPE violations...")
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
        async with pool.acquire() as conn:
            # Find products with recent MAPE > 15%
            rows = await conn.fetch("""
                SELECT product_id, mape, model_name 
                FROM forecast_metrics 
                WHERE mape > 0.15
                AND run_date = (SELECT MAX(run_date) FROM forecast_metrics fm WHERE fm.product_id = forecast_metrics.product_id)
            """)
            
            for row in rows:
                product_id = row['product_id']
                
                # Check if there is already a pending tuning proposal for this product
                pending_tuning = await conn.fetchval("""
                    SELECT 1 FROM hyperparameter_tuning_log 
                    WHERE product_id = $1 AND status = 'proposed' LIMIT 1
                """, product_id)
                
                if pending_tuning:
                    logger.info(f"Skipping MAPE violation for {product_id} as a tuning proposal is already pending.")
                    continue

                logger.warning(f"MAPE violation detected for {product_id} (MAPE: {row['mape']})")
                
                # Trigger supervisor
                query = f"Investigate the high forecast error (MAPE) for {product_id} and tune the model hyperparameters."
                logger.info(f"Triggering supervisor for {product_id}: {query}")
                
                async for event in run_supervisor(user_query=query, user_role="admin"):
                    pass 
                
                logger.info(f"Supervisor successfully triggered and paused at HITL for {product_id}.")
                
        await pool.close()
    except Exception as e:
        logger.error(f"Error checking MAPE: {e}", exc_info=True)

if __name__ == "__main__":
    logger.info("Starting Supply Chain AI Scheduler...")
    scheduler = AsyncIOScheduler()
    
    # Inventory Job (every 60 seconds)
    scheduler.add_job(check_inventory_violations, 'interval', seconds=60, id='inventory_scan')
    
    # MAPE Job (every 5 minutes)
    scheduler.add_job(check_mape_violations, 'interval', minutes=5, id='mape_scan')
    
    scheduler.start()
    
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
