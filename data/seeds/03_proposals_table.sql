-- ─────────────────────────────────────────────────────────────
-- 03_proposals_table.sql
-- Persistent store for agent-generated proposals.
-- The LangGraph HITL node writes here before pausing.
-- Dashboard API reads/updates status here.
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS proposals (
  id                  TEXT PRIMARY KEY,
  type                TEXT NOT NULL CHECK (type IN ('replenishment', 'allocation', 'forecast_tuning')),
  status              TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
  severity            TEXT NOT NULL CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM')),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- What triggered this proposal (denormalized for fast dashboard reads)
  trigger_product_id    TEXT NOT NULL,
  trigger_product_name  TEXT NOT NULL,
  trigger_location      TEXT,
  trigger_metric        TEXT NOT NULL,   -- 'stock_level' | 'mape_pct'
  trigger_current_value NUMERIC NOT NULL,
  trigger_threshold     NUMERIC NOT NULL,

  -- Agent reasoning (shown in ProposalCard)
  agent_reasoning     TEXT NOT NULL,

  -- LangGraph trace metadata
  latency_ms          INT,
  nodes_visited       TEXT[],           -- e.g. ARRAY['supervisor','allocation_replenishment','hitl']
  thread_id           TEXT,             -- LangGraph checkpoint thread_id for resume
  trace_id            TEXT,             -- LangSmith run UUID
  trace_url           TEXT,             -- LangSmith run URL for "View Trace →" link

  -- Type-specific payloads (only one will be non-null per row)
  replenishment_payload  JSONB,
  allocation_payload     JSONB,
  forecast_tuning_payload JSONB
);

-- Index for dashboard queries: pending first, newest first
CREATE INDEX IF NOT EXISTS idx_proposals_status_created
  ON proposals (status, created_at DESC);

-- Auto-update updated_at on any row change
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS proposals_updated_at ON proposals;
CREATE TRIGGER proposals_updated_at
  BEFORE UPDATE ON proposals
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();


-- ─────────────────────────────────────────────────────────────
-- Seed proposals — mirrors Day 1 mock data exactly so the
-- dashboard looks identical but now reads from real Postgres.
-- ─────────────────────────────────────────────────────────────

INSERT INTO proposals (
  id, type, status, severity, created_at,
  trigger_product_id, trigger_product_name, trigger_location,
  trigger_metric, trigger_current_value, trigger_threshold,
  agent_reasoning, latency_ms, nodes_visited, thread_id,
  replenishment_payload, allocation_payload, forecast_tuning_payload
) VALUES

-- prop-001: replenishment, CRITICAL, pending
(
  'prop-001', 'replenishment', 'pending', 'CRITICAL',
  NOW() - INTERVAL '14 minutes',
  'SKU-004', 'Keratin Treatment Mask', 'West',
  'stock_level', 45, 200,
  'Stock at 45 units — 77.5% below reorder point of 200. At current velocity (18 units/day) this location stockouts in 2.5 days. Nearest surplus warehouse (Midwest) holds 620 units of same SKU. However, transfer lead time is 4 days. Recommending emergency PO from Bangalore Bio Products (8-day lead time, lowest cost) alongside partial inter-warehouse transfer to bridge the gap.',
  1842,
  ARRAY['supervisor', 'allocation_replenishment', 'hitl'],
  'thread-prop-001',
  '{
    "purchase_orders": [
      {
        "po_number": "PO-2025-0441",
        "supplier_id": "SUP-003",
        "supplier_name": "Bangalore Bio Products",
        "order_quantity": 500,
        "order_value": 10094.95,
        "lead_time_days": 8,
        "expected_delivery": "2025-05-23"
      }
    ],
    "total_order_value": 10094.95
  }',
  NULL, NULL
),

-- prop-002: allocation, CRITICAL, pending
(
  'prop-002', 'allocation', 'pending', 'CRITICAL',
  NOW() - INTERVAL '14 minutes',
  'SKU-001', 'Vitamin C Brightening Serum', 'Southeast',
  'stock_level', 80, 300,
  'Southeast holding only 80 units against a reorder point of 300 — a 73.3% deficit. Northeast warehouse has 620 units of SKU-001, well above its own reorder point of 300 (surplus: 320 units). Proposing transfer of 160 units Northeast → Southeast. This covers 53% of the deficit immediately while keeping Northeast above safety stock. Remaining gap addressed by standing replenishment cycle.',
  1247,
  ARRAY['supervisor', 'allocation_replenishment', 'hitl'],
  'thread-prop-002',
  NULL,
  '{
    "transfers": [
      {
        "from_location": "Northeast",
        "to_location": "Southeast",
        "transfer_quantity": 160,
        "reason": "Southeast at 73.3% deficit; Northeast has 320-unit surplus above safety stock"
      }
    ]
  }',
  NULL
),

-- prop-003: replenishment, HIGH, pending
(
  'prop-003', 'replenishment', 'pending', 'HIGH',
  NOW() - INTERVAL '2 hours',
  'SKU-010', 'Collagen Eye Cream', 'Northeast',
  'stock_level', 110, 250,
  'Northeast inventory at 110 units, 56% below reorder threshold of 250. Demand forecast shows 15 units/day average with a projected spike during the upcoming promotional window. Without replenishment, stockout probability within 7 days is 82%. Sourcing from Global Wellness Distributors — lowest lead time at 5 days and established relationship for this SKU.',
  2103,
  ARRAY['supervisor', 'allocation_replenishment', 'hitl'],
  'thread-prop-003',
  '{
    "purchase_orders": [
      {
        "po_number": "PO-2025-0442",
        "supplier_id": "SUP-001",
        "supplier_name": "Global Wellness Distributors",
        "order_quantity": 400,
        "order_value": 15960.00,
        "lead_time_days": 5,
        "expected_delivery": "2025-05-20"
      }
    ],
    "total_order_value": 15960.00
  }',
  NULL, NULL
),

-- prop-004: forecast_tuning, HIGH, approved
(
  'prop-004', 'forecast_tuning', 'approved', 'HIGH',
  NOW() - INTERVAL '3 hours',
  'SKU-008', 'Vitamin C Brightening Serum', NULL,
  'mape_pct', 27.89, 15,
  'MAPE of 27.89% is critically high — nearly double the 15% acceptable threshold. Root cause analysis: model is using a 90-day seasonality window but this SKU has strong 30-day promotional cycles. Current changepoint_prior_scale of 0.05 is too rigid to capture rapid demand shifts. Proposing: reduce seasonality_period to 30, increase changepoint_prior_scale to 0.15 to allow faster adaptation. Expected MAPE improvement: ~40% reduction to ~16.7%.',
  3421,
  ARRAY['supervisor', 'forecasting', 'hitl'],
  'thread-prop-004',
  NULL, NULL,
  '{
    "model_name": "Prophet",
    "old_params": {
      "seasonality_period": 90,
      "changepoint_prior_scale": 0.05,
      "seasonality_prior_scale": 10,
      "n_changepoints": 25
    },
    "new_params": {
      "seasonality_period": 30,
      "changepoint_prior_scale": 0.15,
      "seasonality_prior_scale": 10,
      "n_changepoints": 25
    },
    "expected_mape_improvement": "~40% reduction (27.89% → ~16.7%)"
  }'
)

ON CONFLICT (id) DO NOTHING;
