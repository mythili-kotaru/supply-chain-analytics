-- ─────────────────────────────────────────────────────────────
-- Migration 001: Add LangSmith trace columns to proposals table
--
-- WHY a migration and not just editing 03_proposals_table.sql?
-- The Postgres container is already running with the old schema.
-- Docker only runs seed files on first start (when pgdata volume is empty).
-- To add columns to a live DB, we need ALTER TABLE.
--
-- HOW TO RUN:
--   docker exec -i supply_chain_postgres psql -U scai -d supply_chain < data/migrations/001_add_trace_columns.sql
--
-- Or interactively:
--   docker exec -it supply_chain_postgres psql -U scai -d supply_chain
--   \i /path/to/001_add_trace_columns.sql
--
-- The IF NOT EXISTS guards make this idempotent — safe to run multiple times.
-- ─────────────────────────────────────────────────────────────

ALTER TABLE proposals
  ADD COLUMN IF NOT EXISTS trace_id  TEXT,     -- LangSmith run UUID
  ADD COLUMN IF NOT EXISTS trace_url TEXT;     -- LangSmith run URL for "View Trace →" link

-- Verify
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'proposals'
  AND column_name IN ('trace_id', 'trace_url');
