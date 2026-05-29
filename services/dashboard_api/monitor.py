"""
monitor.py — Autonomous monitoring loop (Day 3 + Day 4)

Two APScheduler jobs run inside the FastAPI process:

  inventory_monitor()  → every 60 seconds
  forecast_monitor()   → every 5 minutes

WHY APScheduler instead of a cron job or Celery?
─────────────────────────────────────────────────
Cron would need a separate container + shared filesystem for scripts.
Celery needs a broker (Redis/RabbitMQ) and a worker process.
APScheduler runs inside FastAPI as a background thread — same process,
same DB pool, same logs, one container. Fine for this scale.
In production at CVS Health scale you'd extract this to a dedicated
worker service, but that's premature here.

IDEMPOTENCY — the most important design constraint
────────────────────────────────────────────────────
Both jobs check before inserting:
  "Does a pending proposal already exist for this SKU+location+type?"
If yes → skip. This means you can run the job 1000 times and get
exactly 1 proposal per violation, not 1000. Without this, every
60-second tick would flood the dashboard with duplicate proposals.

Day 4 (complete)
─────────────────
After each INSERT, trigger_langgraph() is called to start the LangGraph
supervisor graph via POST /invoke on the langgraph_agent service.
The graph runs until interrupt_before=["hitl"], then pauses.
The returned thread_id is stored on the proposal row.
When ops manager approves/rejects, the proposals router calls /resume.
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import asyncpg
import httpx

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://scai:scai_password@localhost:5432/supply_chain"
)

# ── LangGraph Agent service URL ───────────────────────────────────────────────
# The langgraph_agent service (port 8004) exposes /invoke and /resume.
# Inside Docker: http://langgraph_agent:8004
# Locally: http://localhost:8004
LANGGRAPH_AGENT_URL = os.getenv("LANGGRAPH_AGENT_URL", "http://localhost:8004")


async def trigger_langgraph(
    proposal_id: str,
    proposal_type: str,
    product_id: str,
    product_name: str,
    location: str | None,
    severity: str,
    trigger_metric: str,
    trigger_value: float,
    trigger_threshold: float,
) -> str | None:
    """
    Fire-and-forget: call POST /invoke on the LangGraph agent service.

    WHY fire-and-forget?
    The monitor job runs on a 60s schedule. We don't want to block the job
    waiting for the LangGraph graph to run (which calls OpenAI, does DB queries,
    etc. — can take 5-15 seconds). We send the request and move on.
    The /invoke endpoint immediately returns the thread_id once the graph pauses.

    If the langgraph_agent service is down, we log a warning and continue.
    The proposal is still created in the DB — ops manager can still see it.
    The HITL just won't have a LangGraph thread backing it until the service
    is restarted and the monitor re-runs (but idempotency prevents double proposals).

    Returns:
        thread_id if successful, None if the service is unavailable.
    """
    payload = {
        "proposal_id": proposal_id,
        "proposal_type": proposal_type,
        "product_id": product_id,
        "product_name": product_name,
        "location": location,
        "severity": severity,
        "trigger_metric": trigger_metric,
        "trigger_value": trigger_value,
        "trigger_threshold": trigger_threshold,
        "user_role": "analyst",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{LANGGRAPH_AGENT_URL}/invoke", json=payload)
            resp.raise_for_status()
            data = resp.json()
            thread_id = data.get("thread_id")
            nodes = data.get("nodes_visited", [])
            summary = data.get("agent_summary", "")
            logger.info(
                f"[langgraph] Graph paused for proposal {proposal_id}: "
                f"thread_id={thread_id} nodes={nodes}"
            )
            logger.info(f"[langgraph] Agent summary: {summary[:200]}")
            return thread_id
    except httpx.ConnectError:
        logger.warning(
            f"[langgraph] langgraph_agent service unreachable at {LANGGRAPH_AGENT_URL}. "
            f"Proposal {proposal_id} created without LangGraph thread."
        )
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"[langgraph] /invoke returned {e.response.status_code}: {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"[langgraph] Unexpected error calling /invoke: {e}", exc_info=True)
        return None

# ── Thresholds ────────────────────────────────────────────────────────────────
MAPE_THRESHOLD = 0.15          # 15% — matches ForecastPanel threshold marker
INVENTORY_CHECK_INTERVAL  = 60    # seconds
FORECAST_CHECK_INTERVAL   = 300   # seconds (5 min)
ANOMALY_CHECK_INTERVAL    = 300   # seconds (5 min) — Day 9 anomaly detection


# ── Agent reasoning templates ─────────────────────────────────────────────────
# These are what the ops manager reads in the ProposalCard.
# Day 4: replace with actual LangGraph-generated reasoning.

def _replenishment_reasoning(product_name: str, location: str,
                              stock: int, reorder: int) -> str:
    deficit_pct = round((reorder - stock) / reorder * 100, 1)
    days_left   = round(stock / max(1, reorder // 30), 1)   # rough estimate
    return (
        f"Autonomous monitor detected {product_name} at {location} has only "
        f"{stock} units — {deficit_pct}% below the reorder threshold of {reorder}. "
        f"At average velocity this location may stockout in approximately {days_left} days. "
        f"Recommend emergency replenishment from lowest lead-time supplier. "
        f"Awaiting approval to generate purchase order."
    )

def _allocation_reasoning(product_name: str, deficit_loc: str,
                           surplus_loc: str, stock: int, reorder: int,
                           transfer_qty: int) -> str:
    deficit_pct = round((reorder - stock) / reorder * 100, 1)
    return (
        f"Autonomous monitor: {product_name} critically low at {deficit_loc} "
        f"({stock} units, {deficit_pct}% below reorder point of {reorder}). "
        f"{surplus_loc} has sufficient surplus. "
        f"Proposing inter-warehouse transfer of {transfer_qty} units "
        f"{surplus_loc} → {deficit_loc} as immediate bridge. "
        f"Awaiting approval to execute transfer."
    )

def _forecast_reasoning(product_name: str, mape_pct: float,
                         model_name: str) -> str:
    return (
        f"Autonomous MAPE scan: {product_name} model ({model_name}) is at "
        f"{mape_pct:.2f}% MAPE — exceeding the 15% acceptable threshold. "
        f"High forecast error leads to either overstocking (capital tied up) "
        f"or understocking (missed sales). Recommend hyperparameter re-tuning. "
        f"Awaiting approval to apply updated model parameters."
    )


# ── Core job: inventory monitor ───────────────────────────────────────────────

async def inventory_monitor(_pool=None) -> None:
    """
    Scans inventory every 60s. For each SKU+location below reorder point
    with no existing pending proposal, inserts a new proposal row.

    Logic:
    1. JOIN inventory + products, filter stock <= reorder_point
    2. LEFT JOIN proposals to check for existing pending proposals
       (both replenishment and allocation) for the same SKU+location
    3. For each unresolved violation → insert a replenishment proposal
    4. Additionally check if another location has surplus of the same SKU
       → if yes, insert an allocation proposal instead (faster than PO)
    """
    logger.info("[monitor] Running inventory scan...")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # Step 1: find all inventory violations with no pending proposal
        violations = await conn.fetch("""
            SELECT
                i.product_id,
                p.product_name,
                p.category,
                i.location,
                i.stock_level,
                i.reorder_point,
                i.max_capacity
            FROM inventory i
            JOIN products p ON p.product_id = i.product_id
            WHERE i.stock_level <= i.reorder_point
              AND NOT EXISTS (
                  SELECT 1 FROM proposals pr
                  WHERE pr.trigger_product_id = i.product_id
                    AND pr.trigger_location   = i.location
                    AND pr.status             = 'pending'
                    AND pr.type IN ('replenishment', 'allocation')
              )
            ORDER BY (i.reorder_point - i.stock_level) DESC
        """)

        if not violations:
            logger.info("[monitor] Inventory scan: no new violations found.")
            return

        logger.info(f"[monitor] Inventory scan: {len(violations)} new violation(s) found.")

        for row in violations:
            product_id   = row["product_id"]
            product_name = row["product_name"]
            location     = row["location"]
            stock        = row["stock_level"]
            reorder      = row["reorder_point"]

            severity = "CRITICAL" if stock <= reorder * 0.5 else "HIGH"

            # Step 2: check if another location has surplus of this SKU
            surplus = await conn.fetchrow("""
                SELECT location, stock_level, reorder_point
                FROM inventory
                WHERE product_id = $1
                  AND location  != $2
                  AND stock_level > reorder_point * 1.2
                ORDER BY (stock_level - reorder_point) DESC
                LIMIT 1
            """, product_id, location)

            proposal_id = str(uuid.uuid4())
            now         = datetime.now(timezone.utc)

            if surplus:
                # Allocation proposal — faster than waiting for a PO
                surplus_loc  = surplus["location"]
                surplus_qty  = surplus["stock_level"] - surplus["reorder_point"]
                transfer_qty = min(reorder - stock, surplus_qty // 2)

                reasoning = _allocation_reasoning(
                    product_name, location, surplus_loc,
                    stock, reorder, transfer_qty
                )

                await conn.execute("""
                    INSERT INTO proposals (
                        id, type, status, severity, created_at,
                        trigger_product_id, trigger_product_name,
                        trigger_location, trigger_metric,
                        trigger_current_value, trigger_threshold,
                        agent_reasoning, nodes_visited,
                        allocation_payload
                    ) VALUES ($1,$2,'pending',$3,$4,$5,$6,$7,'stock_level',$8,$9,$10,$11,$12)
                """,
                    proposal_id, "allocation", severity, now,
                    product_id, product_name, location,
                    float(stock), float(reorder),
                    reasoning,
                    ["supervisor", "allocation_replenishment", "hitl"],
                    json.dumps({
                        "transfers": [{
                            "from_location":    surplus_loc,
                            "to_location":      location,
                            "transfer_quantity": transfer_qty,
                            "reason": (
                                f"{location} at {round((reorder-stock)/reorder*100)}% deficit; "
                                f"{surplus_loc} has {surplus_qty}-unit surplus above safety stock"
                            )
                        }]
                    })
                )
                logger.info(
                    f"[monitor] Created allocation proposal {proposal_id}: "
                    f"{product_name} {surplus_loc}→{location} ({transfer_qty} units)"
                )

                # Day 4: trigger LangGraph — start the graph, pause at HITL
                await trigger_langgraph(
                    proposal_id=proposal_id,
                    proposal_type="allocation",
                    product_id=product_id,
                    product_name=product_name,
                    location=location,
                    severity=severity,
                    trigger_metric="stock_level",
                    trigger_value=float(stock),
                    trigger_threshold=float(reorder),
                )

            else:
                # Replenishment proposal — buy from supplier
                reasoning = _replenishment_reasoning(
                    product_name, location, stock, reorder
                )

                await conn.execute("""
                    INSERT INTO proposals (
                        id, type, status, severity, created_at,
                        trigger_product_id, trigger_product_name,
                        trigger_location, trigger_metric,
                        trigger_current_value, trigger_threshold,
                        agent_reasoning, nodes_visited,
                        replenishment_payload
                    ) VALUES ($1,$2,'pending',$3,$4,$5,$6,$7,'stock_level',$8,$9,$10,$11,$12)
                """,
                    proposal_id, "replenishment", severity, now,
                    product_id, product_name, location,
                    float(stock), float(reorder),
                    reasoning,
                    ["supervisor", "allocation_replenishment", "hitl"],
                    json.dumps({
                        "purchase_orders": [],
                        "total_order_value": 0.0
                    })
                )
                logger.info(
                    f"[monitor] Created replenishment proposal {proposal_id}: "
                    f"{product_name} @ {location} ({stock}/{reorder} units)"
                )

                # Day 4: trigger LangGraph — start the graph, pause at HITL
                await trigger_langgraph(
                    proposal_id=proposal_id,
                    proposal_type="replenishment",
                    product_id=product_id,
                    product_name=product_name,
                    location=location,
                    severity=severity,
                    trigger_metric="stock_level",
                    trigger_value=float(stock),
                    trigger_threshold=float(reorder),
                )

    finally:
        await conn.close()


# ── Core job: forecast monitor ────────────────────────────────────────────────

async def forecast_monitor(_pool=None) -> None:
    """
    Scans forecast_metrics every 5 min. For each product with MAPE > 15%
    and no existing pending forecast_tuning proposal, inserts a new proposal.
    """
    logger.info("[monitor] Running MAPE scan...")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        violations = await conn.fetch("""
            SELECT
                fm.product_id,
                p.product_name,
                fm.model_name,
                fm.mape,
                fm.hyperparameters,
                fm.notes,
                fm.run_date
            FROM forecast_metrics fm
            JOIN products p ON p.product_id = fm.product_id
            WHERE fm.mape > $1
              AND NOT EXISTS (
                  SELECT 1 FROM proposals pr
                  WHERE pr.trigger_product_id = fm.product_id
                    AND pr.status             = 'pending'
                    AND pr.type               = 'forecast_tuning'
              )
            ORDER BY fm.mape DESC
        """, MAPE_THRESHOLD)

        if not violations:
            logger.info("[monitor] MAPE scan: all models within threshold.")
            return

        logger.info(f"[monitor] MAPE scan: {len(violations)} model(s) above threshold.")

        for row in violations:
            product_id   = row["product_id"]
            product_name = row["product_name"]
            model_name   = row["model_name"]
            mape         = float(row["mape"])
            mape_pct     = round(mape * 100, 2)
            raw_hp = row["hyperparameters"]
            if not raw_hp:
                hyperparams = {}
            elif isinstance(raw_hp, str):
                hyperparams = json.loads(raw_hp)
            else:
                hyperparams = dict(raw_hp)

            severity  = "CRITICAL" if mape_pct > 25 else "HIGH"
            reasoning = _forecast_reasoning(product_name, mape_pct, model_name)

            proposal_id = str(uuid.uuid4())
            now         = datetime.now(timezone.utc)

            await conn.execute("""
                INSERT INTO proposals (
                    id, type, status, severity, created_at,
                    trigger_product_id, trigger_product_name,
                    trigger_location, trigger_metric,
                    trigger_current_value, trigger_threshold,
                    agent_reasoning, nodes_visited,
                    forecast_tuning_payload
                ) VALUES ($1,'forecast_tuning','pending',$2,$3,$4,$5,NULL,'mape_pct',$6,$7,$8,$9,$10)
            """,
                proposal_id, severity, now,
                product_id, product_name,
                mape_pct, 15.0,
                reasoning,
                ["supervisor", "forecasting", "hitl"],
                json.dumps({
                    "model_name": model_name,
                    "old_params": hyperparams,
                    "new_params": {},     # Day 4: filled by LangGraph forecasting agent
                    "expected_mape_improvement": "Pending agent analysis"
                })
            )
            logger.info(
                f"[monitor] Created forecast_tuning proposal {proposal_id}: "
                f"{product_name} MAPE={mape_pct}%"
            )

            # Day 4: trigger LangGraph — start the graph, pause at HITL
            await trigger_langgraph(
                proposal_id=proposal_id,
                proposal_type="forecast_tuning",
                product_id=product_id,
                product_name=product_name,
                location=None,
                severity=severity,
                trigger_metric="mape_pct",
                trigger_value=mape_pct,
                trigger_threshold=15.0,
            )

    finally:
        await conn.close()


# ── Core job: anomaly monitor ─────────────────────────────────────────────────

async def anomaly_monitor(_pool=None) -> None:
    """
    Day 9: Run all three anomaly detection rules every 5 minutes.
    Delegates to agents/anomaly_detector.py which handles deduplication
    and auto-proposal creation internally.
    """
    import sys, pathlib
    _here = pathlib.Path(__file__).resolve().parent
    for candidate in [_here] + list(_here.parents):
        if (candidate / "agents").is_dir():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            break

    try:
        from agents.anomaly_detector import run_anomaly_scan
        summary = await run_anomaly_scan(DATABASE_URL)
        if summary["total_new"] > 0:
            logger.info(f"[anomaly] New detections: {summary}")
        else:
            logger.info("[anomaly] Anomaly scan: no new anomalies detected.")
    except Exception as e:
        logger.error(f"[anomaly] Scan failed: {e}", exc_info=True)


# ── APScheduler wrappers ──────────────────────────────────────────────────────
# APScheduler calls sync functions. We wrap each async job in
# asyncio.run() so it gets its own event loop per execution.
# The pool is passed in at scheduler setup time (closure).

def make_sync_job(async_fn):
    """
    Wraps an async monitor function for APScheduler's ThreadPoolExecutor.

    WHY not use AsyncIOScheduler?
    AsyncIOScheduler requires sharing the FastAPI event loop, which can
    cause subtle timing issues when the loop is under load. Running each
    job in its own asyncio.run() is simpler and more predictable for I/O
    bound jobs like DB queries.

    WHY no pool argument?
    asyncpg pools are bound to the event loop they were created on (FastAPI's).
    APScheduler runs each job in a thread that calls asyncio.run(), creating a
    NEW event loop. Passing the pool across loops causes:
      RuntimeError: Future attached to a different loop
    Fix: each job opens its own asyncpg.connect() with a fresh connection,
    tied to its own event loop, and closes it in a finally block.
    """
    def job():
        try:
            asyncio.run(async_fn())
        except Exception as e:
            logger.error(f"[monitor] Job {async_fn.__name__} failed: {e}", exc_info=True)
    return job
