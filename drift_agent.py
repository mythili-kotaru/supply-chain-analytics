import os
import asyncio
import logging
import datetime
import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from agents.supervisor import run_supervisor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("drift_agent")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://scai:scai_password@localhost:5432/supply_chain")

async def analyze_weekly_drift():
    """
    Checks for performance drift over a 7-day period.
    Instead of just reacting to immediate thresholds, this agent checks if a SKU's MAPE
    is slowly degrading over the week, and proactively triggers hyperparameter tuning.
    """
    logger.info("Drift Agent: Analyzing weekly performance drift...")
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
        async with pool.acquire() as conn:
            one_week_ago = datetime.date.today() - datetime.timedelta(days=7)
            
            # Find products where the average MAPE over the last week is significantly higher than previous
            # Simplified query: check if the max MAPE over the last 7 days is > 10% (a stricter threshold than the 15% immediate threshold)
            rows = await conn.fetch("""
                SELECT product_id, MAX(mape) as max_mape, AVG(mape) as avg_mape 
                FROM forecast_metrics 
                WHERE run_date >= $1
                GROUP BY product_id
                HAVING AVG(mape) > 0.10
            """, one_week_ago)
            
            for row in rows:
                product_id = row['product_id']
                logger.warning(f"Drift detected for {product_id} (Weekly Avg MAPE: {row['avg_mape']:.4f})")
                
                # Trigger supervisor with a specific instruction for proactive drift mitigation
                query = f"The weekly average forecast error for {product_id} is drifting high ({row['avg_mape']:.4f}). Proactively tune the model hyperparameters to prevent a critical failure."
                logger.info(f"Triggering supervisor for {product_id}: {query}")
                
                async for event in run_supervisor(user_query=query, user_role="admin"):
                    pass 
                
                logger.info(f"Supervisor successfully triggered for proactive tuning of {product_id}.")
                
        await pool.close()
    except Exception as e:
        logger.error(f"Error checking drift: {e}", exc_info=True)

if __name__ == "__main__":
    logger.info("Starting Supply Chain AI Drift Agent...")
    scheduler = AsyncIOScheduler()
    
    # Analyze weekly drift once a day
    scheduler.add_job(analyze_weekly_drift, 'interval', days=1, id='weekly_drift')
    
    scheduler.start()
    
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
