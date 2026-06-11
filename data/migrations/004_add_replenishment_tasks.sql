-- ─────────────────────────────────────────────────────────────
-- Migration 004: Add replenishment_tasks table
--
-- Exposes persistent storage for the Replenishment Agent tasks,
-- mirroring the layout of allocation_tasks.
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS replenishment_tasks (
    task_id         TEXT PRIMARY KEY,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    product_id      TEXT,
    status          TEXT DEFAULT 'pending',  -- 'pending','in_progress','completed','failed','executed'
    input_payload   JSONB,
    result_payload  JSONB,
    error           TEXT
);

-- Index for status lookups
CREATE INDEX IF NOT EXISTS idx_replenishment_tasks_status ON replenishment_tasks(status);

-- Verify
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'replenishment_tasks'
ORDER BY ordinal_position;
