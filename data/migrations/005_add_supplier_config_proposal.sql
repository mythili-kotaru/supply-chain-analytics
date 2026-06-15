-- ─────────────────────────────────────────────────────────────
-- Migration 005: Add supplier_config type to proposals
--
-- Updates check constraint to allow 'supplier_config' proposal type
-- and adds supplier_config_payload column.
-- ─────────────────────────────────────────────────────────────

-- Drop the old constraint
ALTER TABLE proposals DROP CONSTRAINT IF EXISTS proposals_type_check;

-- Add the updated constraint
ALTER TABLE proposals ADD CONSTRAINT proposals_type_check 
  CHECK (type IN ('replenishment', 'allocation', 'forecast_tuning', 'supplier_config'));

-- Add the payload column if it doesn't exist
ALTER TABLE proposals ADD COLUMN IF NOT EXISTS supplier_config_payload JSONB;

-- Verify columns
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'proposals'
ORDER BY ordinal_position;
