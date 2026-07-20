-- ─────────────────────────────────────────────────────────────
-- Migration 008: Add supplier_performance_log table
--
-- Tracks evaluations of supplier lead times, delivery rates, and
-- defect rates dynamically over time.
--
-- Usage:
--   docker exec -i supply_chain_postgres psql -U scai -d supply_chain < data/migrations/008_add_supplier_performance_log.sql
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS supplier_performance_log (
    log_id                  SERIAL PRIMARY KEY,
    supplier_id             TEXT NOT NULL REFERENCES suppliers(supplier_id) ON DELETE CASCADE,
    evaluation_date         TIMESTAMPTZ DEFAULT NOW(),
    avg_actual_lead_time    NUMERIC(5, 2),
    late_delivery_rate      NUMERIC(5, 4),
    defect_rate             NUMERIC(5, 4),
    status                  TEXT NOT NULL  -- 'healthy', 'warning', 'critical'
);

-- Index for supplier lookups
CREATE INDEX IF NOT EXISTS idx_supplier_performance_supplier ON supplier_performance_log(supplier_id);

-- Verify
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'supplier_performance_log'
ORDER BY ordinal_position;
