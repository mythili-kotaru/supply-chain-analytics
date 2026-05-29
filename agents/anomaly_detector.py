"""
agents/anomaly_detector.py
──────────────────────────
Day 9 — Anomaly Detection

Proactively scans inventory and forecast tables for unusual patterns
and writes detections to anomaly_events. For severe anomalies it also
auto-creates proposals so the HITL flow kicks in automatically.

THREE DETECTION RULES:

  1. STOCK DROP
     Trigger: stock_level has fallen more than 30% below the reorder_point
     (i.e. not just low, but *significantly* below threshold).
     Severity: CRITICAL if <50% of reorder_point, HIGH otherwise.
     Why: A product at 30% of its reorder point is at immediate stockout risk.
     Baseline: the product's reorder_point (designed minimum stock level).

  2. DEMAND SPIKE
     Trigger: recent 7-day order quantity is >2x the 30-day rolling average.
     Severity: CRITICAL if >3x average, HIGH if >2x.
     Why: Demand spikes exhaust inventory and aren't captured by static reorder points.
     Baseline: 30-day rolling average order quantity per product/region.

  3. MAPE REGRESSION
     Trigger: the latest forecast_metrics run has MAPE >5% worse than the
     previous run for the same product/model.
     Severity: CRITICAL if MAPE regression >10%, HIGH if >5%.
     Why: Model drift means predictions are getting less reliable over time.
     Baseline: the previous run's MAPE for the same product+model.

DEDUPLICATION:
  Each rule checks whether an unacknowledged anomaly of the same type
  already exists for the same product+location within the past 6 hours.
  If one exists, we skip inserting — avoids flooding the feed on every scan.

AUTO-PROPOSAL CREATION:
  For CRITICAL anomalies only, the detector inserts a proposal row so the
  HITL dashboard shows it immediately. The proposal is only created if no
  open (pending/approved) proposal for that product already exists.
"""

import logging
import asyncpg
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────

# Stock drop: how far below reorder_point before we flag
STOCK_DROP_CRITICAL_PCT = 50   # stock < 50% of reorder_point → CRITICAL
STOCK_DROP_HIGH_PCT     = 70   # stock < 70% of reorder_point → HIGH
STOCK_DROP_MIN_PCT      = 85   # stock < 85% of reorder_point → minimum to flag

# Demand spike: multiplier vs 30-day rolling average
DEMAND_SPIKE_CRITICAL_X = 3.0  # >3x average → CRITICAL
DEMAND_SPIKE_HIGH_X     = 2.0  # >2x average → HIGH

# MAPE regression: absolute percentage point worsening
MAPE_REGRESSION_CRITICAL_PP = 10.0  # MAPE worsened by >10pp → CRITICAL
MAPE_REGRESSION_HIGH_PP     = 5.0   # MAPE worsened by >5pp → HIGH

# Dedup window: don't re-flag the same issue within this many hours
DEDUP_WINDOW_HOURS = 6


async def _already_flagged(conn: asyncpg.Connection, anomaly_type: str,
                            product_id: str, location: str | None) -> bool:
    """Return True if an unacknowledged anomaly of this type already exists within the dedup window."""
    row = await conn.fetchrow("""
        SELECT 1 FROM anomaly_events
        WHERE anomaly_type = $1
          AND product_id   = $2
          AND (location = $3 OR ($3 IS NULL AND location IS NULL))
          AND acknowledged = FALSE
          AND detected_at > NOW() - INTERVAL '6 hours'
        LIMIT 1
    """, anomaly_type, product_id, location)
    return row is not None


async def _open_proposal_exists(conn: asyncpg.Connection, product_id: str) -> bool:
    """Return True if there's already a pending/approved proposal for this product."""
    row = await conn.fetchrow("""
        SELECT 1 FROM proposals
        WHERE trigger_product_id = $1
          AND status IN ('pending', 'approved')
        LIMIT 1
    """, product_id)
    return row is not None


async def _insert_anomaly(conn: asyncpg.Connection, *,
                           anomaly_type: str,
                           severity: str,
                           product_id: str,
                           location: str | None,
                           metric_name: str,
                           metric_value: float,
                           baseline_value: float,
                           deviation_pct: float,
                           anomaly_score: float,
                           description: str) -> int:
    """Insert one anomaly_events row and return its id."""
    row = await conn.fetchrow("""
        INSERT INTO anomaly_events
            (anomaly_type, severity, product_id, location,
             metric_name, metric_value, baseline_value,
             deviation_pct, anomaly_score, description)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
        RETURNING id
    """, anomaly_type, severity, product_id, location,
        metric_name, metric_value, baseline_value,
        round(deviation_pct, 2), round(anomaly_score, 4), description)
    return row["id"]


async def _create_proposal(conn: asyncpg.Connection, *,
                            product_id: str,
                            product_name: str,
                            location: str | None,
                            proposal_type: str,
                            severity: str,
                            trigger_metric: str,
                            trigger_value: float,
                            trigger_threshold: float,
                            agent_reasoning: str) -> str | None:
    """
    Insert a proposal row so the HITL dashboard picks it up.
    Returns the new proposal UUID, or None if already exists.
    """
    import uuid, json
    if await _open_proposal_exists(conn, product_id):
        logger.info(f"Skipping auto-proposal for {product_id} — open proposal already exists")
        return None

    proposal_id = str(uuid.uuid4())

    # Build a minimal payload depending on type
    if proposal_type == "replenishment":
        payload_col = "replenishment_payload"
        payload_val = json.dumps({
            "purchase_orders": [],
            "total_order_value": 0,
            "supplier_name": "TBD — agent will determine",
            "lead_time_days": 0,
            "expected_delivery": "TBD"
        })
    elif proposal_type == "allocation":
        payload_col = "allocation_payload"
        payload_val = json.dumps({"transfers": [], "total_units": 0})
    else:
        payload_col = "forecast_tuning_payload"
        payload_val = json.dumps({
            "model_name": "xgboost_v1",
            "old_params": {},
            "new_params": {},
            "expected_mape_improvement": "TBD — agent will determine"
        })

    await conn.execute(f"""
        INSERT INTO proposals (
            id, type, status, severity, created_at,
            trigger_product_id, trigger_product_name,
            trigger_location, trigger_metric,
            trigger_current_value, trigger_threshold,
            agent_reasoning, nodes_visited,
            {payload_col}
        ) VALUES (
            $1, $2, 'pending', $3, NOW(),
            $4, $5, $6, $7, $8, $9, $10,
            ARRAY['anomaly_detector'],
            $11::jsonb
        )
    """, proposal_id, proposal_type, severity,
        product_id, product_name, location,
        trigger_metric, trigger_value, trigger_threshold,
        agent_reasoning, payload_val)

    logger.info(f"Auto-created proposal {proposal_id} for {product_id} ({proposal_type})")
    return proposal_id


async def _link_anomaly_to_proposal(conn: asyncpg.Connection, anomaly_id: int, proposal_id: str):
    await conn.execute(
        "UPDATE anomaly_events SET proposal_id = $1 WHERE id = $2",
        proposal_id, anomaly_id
    )


# ── Detection rule 1: Stock drop ──────────────────────────────────────────────

async def detect_stock_drops(conn: asyncpg.Connection) -> int:
    """
    Find inventory rows where stock_level is significantly below reorder_point.
    Returns count of new anomalies inserted.
    """
    rows = await conn.fetch("""
        SELECT
            i.product_id,
            p.product_name,
            i.location,
            i.stock_level,
            i.reorder_point,
            CASE WHEN i.reorder_point > 0
                 THEN (i.stock_level::float / i.reorder_point) * 100
                 ELSE 0
            END AS stock_pct_of_reorder
        FROM inventory i
        JOIN products p ON p.product_id = i.product_id
        WHERE i.reorder_point > 0
          AND i.stock_level < i.reorder_point * ($1 / 100.0)
    """, float(STOCK_DROP_MIN_PCT))

    count = 0
    for row in rows:
        product_id = row["product_id"]
        location   = row["location"]
        stock_pct  = float(row["stock_pct_of_reorder"])
        stock_lvl  = float(row["stock_level"])
        reorder    = float(row["reorder_point"])

        # Determine severity
        if stock_pct < STOCK_DROP_CRITICAL_PCT:
            severity = "CRITICAL"
        else:
            severity = "HIGH"

        if await _already_flagged(conn, "stock_drop", product_id, location):
            continue

        deviation_pct = reorder - stock_lvl   # units below reorder point
        anomaly_score = max(0, min(1, 1 - (stock_pct / 100)))

        description = (
            f"{row['product_name']} at {location} has only {int(stock_lvl)} units "
            f"({stock_pct:.0f}% of reorder point {int(reorder)}). "
            f"Immediate replenishment or reallocation recommended."
        )

        anomaly_id = await _insert_anomaly(
            conn,
            anomaly_type="stock_drop",
            severity=severity,
            product_id=product_id,
            location=location,
            metric_name="stock_level",
            metric_value=stock_lvl,
            baseline_value=reorder,
            deviation_pct=-(100 - stock_pct),  # negative = below baseline
            anomaly_score=anomaly_score,
            description=description,
        )

        # Auto-create proposal for CRITICAL stock drops
        if severity == "CRITICAL":
            proposal_id = await _create_proposal(
                conn,
                product_id=product_id,
                product_name=row["product_name"],
                location=location,
                proposal_type="replenishment",
                severity=severity,
                trigger_metric="stock_level",
                trigger_value=stock_lvl,
                trigger_threshold=reorder,
                agent_reasoning=(
                    f"Anomaly detector: {row['product_name']} at {location} is at "
                    f"{stock_pct:.0f}% of reorder point ({int(stock_lvl)}/{int(reorder)} units). "
                    f"Auto-generated replenishment proposal."
                )
            )
            if proposal_id:
                await _link_anomaly_to_proposal(conn, anomaly_id, proposal_id)

        logger.info(f"[stock_drop] {product_id} @ {location}: {stock_lvl}/{reorder} ({severity})")
        count += 1

    return count


# ── Detection rule 2: Demand spike ───────────────────────────────────────────

async def detect_demand_spikes(conn: asyncpg.Connection) -> int:
    """
    Compare last 7 days of orders vs the 30-day rolling average.
    Flags products/regions where recent demand is unusually high.
    """
    rows = await conn.fetch("""
        WITH recent AS (
            SELECT product_id, region,
                   SUM(order_quantity) AS qty_7d,
                   COUNT(*) AS orders_7d
            FROM supply_chain_records
            WHERE order_date >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY product_id, region
        ),
        baseline AS (
            SELECT product_id, region,
                   SUM(order_quantity) / 30.0 * 7 AS expected_7d
            FROM supply_chain_records
            WHERE order_date >= CURRENT_DATE - INTERVAL '30 days'
              AND order_date < CURRENT_DATE - INTERVAL '7 days'
            GROUP BY product_id, region
        )
        SELECT
            r.product_id,
            p.product_name,
            r.region,
            r.qty_7d,
            b.expected_7d,
            CASE WHEN b.expected_7d > 0
                 THEN r.qty_7d / b.expected_7d
                 ELSE NULL
            END AS demand_multiplier
        FROM recent r
        JOIN baseline b ON b.product_id = r.product_id AND b.region = r.region
        JOIN products p ON p.product_id = r.product_id
        WHERE b.expected_7d > 0
          AND r.qty_7d > b.expected_7d * $1
    """, DEMAND_SPIKE_HIGH_X)

    count = 0
    for row in rows:
        product_id  = row["product_id"]
        location    = row["region"]
        multiplier  = float(row["demand_multiplier"])
        qty_7d      = float(row["qty_7d"])
        expected    = float(row["expected_7d"])

        severity = "CRITICAL" if multiplier >= DEMAND_SPIKE_CRITICAL_X else "HIGH"

        if await _already_flagged(conn, "demand_spike", product_id, location):
            continue

        deviation_pct = (multiplier - 1) * 100
        anomaly_score = min(1.0, (multiplier - 1) / 3)

        description = (
            f"{row['product_name']} in {location}: last 7-day demand was "
            f"{int(qty_7d)} units vs expected {expected:.0f} "
            f"({multiplier:.1f}x normal). Inventory may be depleted faster than planned."
        )

        anomaly_id = await _insert_anomaly(
            conn,
            anomaly_type="demand_spike",
            severity=severity,
            product_id=product_id,
            location=location,
            metric_name="demand_units_7d",
            metric_value=qty_7d,
            baseline_value=expected,
            deviation_pct=deviation_pct,
            anomaly_score=anomaly_score,
            description=description,
        )

        if severity == "CRITICAL":
            proposal_id = await _create_proposal(
                conn,
                product_id=product_id,
                product_name=row["product_name"],
                location=location,
                proposal_type="allocation",
                severity=severity,
                trigger_metric="demand_multiplier",
                trigger_value=round(multiplier, 2),
                trigger_threshold=DEMAND_SPIKE_CRITICAL_X,
                agent_reasoning=(
                    f"Anomaly detector: {row['product_name']} in {location} has a "
                    f"{multiplier:.1f}x demand spike. Consider reallocation from surplus regions."
                )
            )
            if proposal_id:
                await _link_anomaly_to_proposal(conn, anomaly_id, proposal_id)

        logger.info(f"[demand_spike] {product_id} @ {location}: {multiplier:.1f}x ({severity})")
        count += 1

    return count


# ── Detection rule 3: MAPE regression ────────────────────────────────────────

async def detect_mape_regressions(conn: asyncpg.Connection) -> int:
    """
    Compare the latest forecast_metrics run against the previous one.
    Flags models where MAPE got worse by more than 5 percentage points.
    """
    rows = await conn.fetch("""
        WITH ranked AS (
            SELECT
                product_id,
                model_name,
                mape,
                run_date,
                LAG(mape) OVER (
                    PARTITION BY product_id, model_name
                    ORDER BY run_date ASC
                ) AS prev_mape,
                LAG(run_date) OVER (
                    PARTITION BY product_id, model_name
                    ORDER BY run_date ASC
                ) AS prev_run_date
            FROM forecast_metrics
        )
        SELECT
            r.product_id,
            p.product_name,
            r.model_name,
            (r.mape * 100)::numeric(6,2)      AS mape_pct,
            (r.prev_mape * 100)::numeric(6,2)  AS prev_mape_pct,
            ((r.mape - r.prev_mape) * 100)::numeric(6,2) AS regression_pp,
            r.run_date,
            r.prev_run_date
        FROM ranked r
        JOIN products p ON p.product_id = r.product_id
        WHERE r.prev_mape IS NOT NULL
          AND (r.mape - r.prev_mape) * 100 > $1
        ORDER BY regression_pp DESC
    """, MAPE_REGRESSION_HIGH_PP)

    count = 0
    for row in rows:
        product_id    = row["product_id"]
        mape_pct      = float(row["mape_pct"])
        prev_mape_pct = float(row["prev_mape_pct"])
        regression_pp = float(row["regression_pp"])

        severity = "CRITICAL" if regression_pp >= MAPE_REGRESSION_CRITICAL_PP else "HIGH"

        if await _already_flagged(conn, "mape_regression", product_id, None):
            continue

        anomaly_score = min(1.0, regression_pp / 20)
        description = (
            f"{row['product_name']} ({row['model_name']}): MAPE worsened from "
            f"{prev_mape_pct}% to {mape_pct}% (+{regression_pp:.1f}pp) "
            f"since {row['prev_run_date']}. Model drift detected — consider re-tuning."
        )

        anomaly_id = await _insert_anomaly(
            conn,
            anomaly_type="mape_regression",
            severity=severity,
            product_id=product_id,
            location=None,
            metric_name="mape_pct",
            metric_value=mape_pct,
            baseline_value=prev_mape_pct,
            deviation_pct=regression_pp,
            anomaly_score=anomaly_score,
            description=description,
        )

        if severity == "CRITICAL":
            proposal_id = await _create_proposal(
                conn,
                product_id=product_id,
                product_name=row["product_name"],
                location=None,
                proposal_type="forecast_tuning",
                severity=severity,
                trigger_metric="mape_pct",
                trigger_value=mape_pct,
                trigger_threshold=15.0,
                agent_reasoning=(
                    f"Anomaly detector: {row['product_name']} MAPE regressed "
                    f"{prev_mape_pct}% → {mape_pct}% (+{regression_pp:.1f}pp). "
                    f"Auto-generated forecast tuning proposal."
                )
            )
            if proposal_id:
                await _link_anomaly_to_proposal(conn, anomaly_id, proposal_id)

        logger.info(f"[mape_regression] {product_id}: {prev_mape_pct}% → {mape_pct}% (+{regression_pp:.1f}pp) ({severity})")
        count += 1

    return count


# ── Main scanner ──────────────────────────────────────────────────────────────

async def run_anomaly_scan(database_url: str) -> dict:
    """
    Run all three detection rules against the live DB.
    Called by the scheduler every N minutes.
    Returns a summary dict for logging.
    """
    conn = await asyncpg.connect(database_url)
    try:
        stock_count  = await detect_stock_drops(conn)
        demand_count = await detect_demand_spikes(conn)
        mape_count   = await detect_mape_regressions(conn)

        total = stock_count + demand_count + mape_count
        summary = {
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "stock_drop":      stock_count,
            "demand_spike":    demand_count,
            "mape_regression": mape_count,
            "total_new":       total,
        }
        logger.info(f"Anomaly scan complete: {summary}")
        return summary
    finally:
        await conn.close()
