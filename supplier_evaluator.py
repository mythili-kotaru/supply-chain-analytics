import os
import asyncio
import logging
import asyncpg
from notifier import send_alert

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(name)s: %(message)s"
)
logger = logging.getLogger("supplier_evaluator")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://scai:scai_password@localhost:5432/supply_chain")

async def evaluate_supplier_performance():
    logger.info("Evaluating supplier performance from historical records...")
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
        async with pool.acquire() as conn:
            # Calculate rolling metrics based on supply_chain_records vs promised lead_time_days
            rows = await conn.fetch("""
                SELECT 
                    s.supplier_id,
                    s.supplier_name,
                    s.lead_time_days AS promised_lead_time,
                    s.defect_rate AS supplier_defect_rate,
                    AVG(scr.delivery_date - scr.order_date) AS avg_actual_lead_time,
                    CASE 
                        WHEN COUNT(scr.record_id) > 0 THEN 
                            COUNT(CASE WHEN (scr.delivery_date - scr.order_date) > s.lead_time_days THEN 1 END)::NUMERIC / COUNT(scr.record_id)
                        ELSE 0 
                    END AS late_delivery_rate
                FROM suppliers s
                LEFT JOIN supply_chain_records scr ON s.supplier_id = scr.supplier_id
                GROUP BY s.supplier_id, s.supplier_name, s.lead_time_days, s.defect_rate
            """)
            
            for row in rows:
                supplier_id = row['supplier_id']
                supplier_name = row['supplier_name']
                promised = row['promised_lead_time']
                actual_avg = row['avg_actual_lead_time']
                late_rate = row['late_delivery_rate']
                defect_rate = row['supplier_defect_rate']
                
                # Determine status
                # If late rate > 25% or actual average is 3+ days over promised, it's critical
                if late_rate > 0.25 or (actual_avg and actual_avg - promised > 3):
                    status = 'critical'
                elif late_rate > 0.10 or (actual_avg and actual_avg - promised > 1):
                    status = 'warning'
                else:
                    status = 'healthy'
                    
                actual_avg_str = f"{actual_avg:.2f} days" if actual_avg is not None else "N/A"
                logger.info(
                    f"Supplier: {supplier_name} ({supplier_id}) | "
                    f"Promised: {promised} days | "
                    f"Actual Avg: {actual_avg_str} | "
                    f"Late Rate: {late_rate * 100:.1f}% | "
                    f"Status: {status}"
                )
                
                # Save check results in the log table
                await conn.execute("""
                    INSERT INTO supplier_performance_log 
                    (supplier_id, avg_actual_lead_time, late_delivery_rate, defect_rate, status)
                    VALUES ($1, $2, $3, $4, $5)
                """, supplier_id, actual_avg, late_rate, defect_rate, status)
                
                # If warning or critical, trigger Slack alert
                if status in ('warning', 'critical'):
                    emoji = "⚠️" if status == 'warning' else "🚨"
                    alert_msg = (
                        f"{emoji} *Supplier Performance Alert*: {supplier_name} ({supplier_id}) is marked *{status.upper()}*.\n"
                        f"- Promised Lead Time: {promised} days\n"
                        f"- Actual Avg Lead Time: {actual_avg:.1f} days\n"
                        f"- Late Delivery Rate: {late_rate * 100:.1f}%\n"
                        f"- Defect Rate: {defect_rate * 100:.2f}%"
                    )
                    send_alert(alert_msg)
                    
        await pool.close()
    except Exception as e:
        logger.error(f"Error evaluating supplier performance: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(evaluate_supplier_performance())
