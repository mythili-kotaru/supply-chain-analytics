-- ─────────────────────────────────────────────────────────────
-- Migration 002: Add drift detection columns to hyperparameter_tuning_log
--
-- WHY drift detection?
-- After approving a hyperparameter change, we want to know if it actually
-- improved the forecast. We record:
--   pre_mape  — MAPE before tuning (from forecast_metrics at approval time)
--   post_mape — MAPE after re-running the model with new params
--   mape_delta — improvement (positive = better, negative = worse)
--   simulated — TRUE if post_mape was simulated (no live model available)
--
-- HOW TO RUN:
--   docker exec -i supply_chain_postgres psql -U scai -d supply_chain < data/migrations/002_add_drift_columns.sql
--
-- Idempotent — safe to run multiple times.
-- ─────────────────────────────────────────────────────────────

ALTER TABLE hyperparameter_tuning_log
  ADD COLUMN IF NOT EXISTS pre_mape    NUMERIC(6,4),   -- MAPE before tuning
  ADD COLUMN IF NOT EXISTS post_mape   NUMERIC(6,4),   -- MAPE after tuning
  ADD COLUMN IF NOT EXISTS mape_delta  NUMERIC(6,4),   -- pre_mape - post_mape (positive = improvement)
  ADD COLUMN IF NOT EXISTS simulated   BOOLEAN DEFAULT FALSE,  -- TRUE if post_mape was simulated
  ADD COLUMN IF NOT EXISTS evaluated_at TIMESTAMPTZ;   -- when drift was measured

-- Verify
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'hyperparameter_tuning_log'
  AND column_name IN ('pre_mape', 'post_mape', 'mape_delta', 'simulated', 'evaluated_at');
