import os
import asyncio
import datetime
import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://scai:scai_password@localhost:5432/supply_chain")

async def generate_daily_digest():
    print("Generating Daily Digest...")
    try:
        pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
        async with pool.acquire() as conn:
            # Get data from the last 24 hours
            now = datetime.datetime.now()
            yesterday = now - datetime.timedelta(days=1)
            
            # 1. Fetch Allocation / Replenishment Tasks
            tasks = await conn.fetch("""
                SELECT task_id, product_id, region, status, created_at, error
                FROM allocation_tasks
                WHERE created_at >= $1
                ORDER BY created_at DESC
            """, yesterday)
            
            # 2. Fetch Forecast Tuning Actions
            tunings = await conn.fetch("""
                SELECT product_id, status, proposed_at, pre_mape, post_mape, mape_delta, rationale
                FROM hyperparameter_tuning_log
                WHERE proposed_at >= $1
                ORDER BY proposed_at DESC
            """, yesterday)

        await pool.close()

        # Build HTML content
        html_content = f"""
        <html>
        <head>
            <title>Supply Chain AI - Daily Ops Digest</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 2rem; color: #333; }}
                h1 {{ color: #1e3a8a; }}
                h2 {{ color: #2563eb; border-bottom: 2px solid #e5e7eb; padding-bottom: 0.5rem; }}
                table {{ width: 100%; border-collapse: collapse; margin-bottom: 2rem; }}
                th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid #e5e7eb; }}
                th {{ background-color: #f3f4f6; }}
                .status-completed {{ color: #166534; font-weight: bold; }}
                .status-pending {{ color: #b45309; font-weight: bold; }}
                .status-failed {{ color: #991b1b; font-weight: bold; }}
            </style>
        </head>
        <body>
            <h1>Supply Chain AI - Daily Ops Digest</h1>
            <p><strong>Report generated:</strong> {now.strftime("%Y-%m-%d %H:%M:%S")}</p>
            <p>This report summarizes the actions proposed and executed by the AI agents over the last 24 hours.</p>

            <h2>A2A Tasks (Allocation & Replenishment)</h2>
            <table>
                <tr>
                    <th>Time</th>
                    <th>Task ID</th>
                    <th>Product ID</th>
                    <th>Region</th>
                    <th>Status</th>
                </tr>
        """
        
        for t in tasks:
            status_class = f"status-{t['status'].lower()}" if t['status'] else ""
            html_content += f"""
                <tr>
                    <td>{t['created_at'].strftime("%Y-%m-%d %H:%M")}</td>
                    <td>{t['task_id'][:8]}...</td>
                    <td>{t['product_id']}</td>
                    <td>{t['region'] or 'N/A'}</td>
                    <td class="{status_class}">{t['status']}</td>
                </tr>
            """
            
        if not tasks:
            html_content += "<tr><td colspan='5'>No A2A tasks recorded in the last 24 hours.</td></tr>"

        html_content += """
            </table>

            <h2>Forecast Model Tuning</h2>
            <table>
                <tr>
                    <th>Time</th>
                    <th>Product ID</th>
                    <th>Status</th>
                    <th>Pre-MAPE</th>
                    <th>Post-MAPE</th>
                    <th>Improvement</th>
                </tr>
        """
        
        for t in tunings:
            pre_mape = f"{t['pre_mape'] * 100:.2f}%" if t['pre_mape'] else "N/A"
            post_mape = f"{t['post_mape'] * 100:.2f}%" if t['post_mape'] else "N/A"
            delta = f"{t['mape_delta'] * 100:.2f}%" if t['mape_delta'] else "N/A"
            
            html_content += f"""
                <tr>
                    <td>{t['proposed_at'].strftime("%Y-%m-%d %H:%M")}</td>
                    <td>{t['product_id']}</td>
                    <td>{t['status']}</td>
                    <td>{pre_mape}</td>
                    <td>{post_mape}</td>
                    <td style="color: #166534; font-weight: bold;">{delta}</td>
                </tr>
            """
            
        if not tunings:
            html_content += "<tr><td colspan='6'>No forecast tuning actions recorded in the last 24 hours.</td></tr>"

        html_content += """
            </table>
        </body>
        </html>
        """

        report_path = os.path.join(os.path.dirname(__file__), "data", f"daily_digest_{now.strftime('%Y%m%d')}.html")
        with open(report_path, "w") as f:
            f.write(html_content)
        
        print(f"Daily Digest generated successfully at: {report_path}")

    except Exception as e:
        print(f"Error generating daily digest: {e}")

if __name__ == "__main__":
    asyncio.run(generate_daily_digest())
