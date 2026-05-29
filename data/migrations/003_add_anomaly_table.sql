-- ─────────────────────────────────────────────────────────────
-- Migration 003: Add anomaly_events table (Day 9 — Anomaly Detection)
--
-- WHY a separate table and not reusing proposals?
-- Proposals require human approval — they're discrete, actionable items.
-- Anomaly events are a continuous stream of detections (many per minute).
-- Most anomalies don't warrant a proposal — they're informational signals.
-- Separating them keeps the proposals table clean and the feed fast.
--
-- HOW anomaly_events relate to proposals:
-- When an anomaly is severe enough, the detector creates BOTH:
--   1. An anomaly_event row (the raw detection, always)
--   2. A proposal row (only if severity >= CRITICAL and no open proposal exists)
-- The proposal_id FK links them so the UI can cross-reference.
--
-- HOW TO RUN:
--   docker exec -i supply_chain_postgres psql -U scai -d supply_chain < data/migrations/003_add_anomaly_table.sql
--
-- Idempotent — safe to run multiple times.
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS anomaly_events (
    id              SERIAL PRIMARY KEY,
    detected_at     TIMESTAMPTZ DEFAULT NOW(),
    anomaly_type    TEXT NOT NULL,    -- 'stock_drop' | 'demand_spike' | 'mape_regression'
    severity        TEXT NOT NULL,    -- 'CRITICAL' | 'HIGH' | 'MEDIUM'
    product_id      TEXT REFERENCES products(product_id),
    location        TEXT,             -- warehouse/region (nullable for forecast anomalies)
    metric_name     TEXT NOT NULL,    -- 'stock_level' | 'demand_units' | 'mape_pct'
    metric_value    NUMERIC(12, 4),   -- the current value that triggered detection
    baseline_value  NUMERIC(12, 4),   -- the expected/historical baseline
    deviation_pct   NUMERIC(8, 2),    -- % deviation from baseline (positive = above)
    anomaly_score   NUMERIC(6, 4),    -- 0–1 normalized score (1 = most anomalous)
    description     TEXT,             -- human-readable explanation
    proposal_id     TEXT,             -- FK to proposals.id if a proposal was created
    acknowledged    BOOLEAN DEFAULT FALSE,  -- ops manager dismissed this alert
    acknowledged_at TIMESTAMPTZ
);

-- Index for dashboard feed (most recent first, unacknowledged first)
CREATE INDEX IF NOT EXISTS idx_anomaly_detected_at
    ON anomaly_events(detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_anomaly_product
    ON anomaly_events(product_id, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_anomaly_unacked
    ON anomaly_events(acknowledged, severity, detected_at DESC);

-- Verify
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'anomaly_events'
ORDER BY ordinal_position;
