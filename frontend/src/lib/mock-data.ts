// lib/mock-data.ts
// Exact mirror of the Postgres seed data from 02_seed_data.sql
// Day 2: replace these with real API calls to the FastAPI dashboard backend.

import type {
  InventoryAlert,
  ForecastAlert,
  Proposal,
  DashboardStats,
  TraceStep,
} from "@/types";

// ─── Inventory alerts (from inventory table, status = CRITICAL or LOW) ──
export const MOCK_INVENTORY_ALERTS: InventoryAlert[] = [
  {
    product_id: "SKU-001",
    product_name: "Moisturizing Face Cream",
    category: "skincare",
    location: "Southeast",
    stock_level: 80,
    reorder_point: 100,
    max_capacity: 1000,
    buffer_units: -20,
    capacity_pct: 8.0,
    status: "CRITICAL",
    last_updated: "2026-05-18T08:00:00Z",
  },
  {
    product_id: "SKU-004",
    product_name: "Keratin Hair Mask",
    category: "haircare",
    location: "West",
    stock_level: 95,
    reorder_point: 150,
    max_capacity: 600,
    buffer_units: -55,
    capacity_pct: 15.8,
    status: "CRITICAL",
    last_updated: "2026-05-18T08:00:00Z",
  },
  {
    product_id: "SKU-006",
    product_name: "Foundation SPF30",
    category: "cosmetics",
    location: "Southeast",
    stock_level: 180,
    reorder_point: 200,
    max_capacity: 900,
    buffer_units: -20,
    capacity_pct: 20.0,
    status: "CRITICAL",
    last_updated: "2026-05-18T08:00:00Z",
  },
  {
    product_id: "SKU-010",
    product_name: "Conditioner Argan Oil",
    category: "haircare",
    location: "Northeast",
    stock_level: 110,
    reorder_point: 150,
    max_capacity: 700,
    buffer_units: -40,
    capacity_pct: 15.7,
    status: "CRITICAL",
    last_updated: "2026-05-18T08:00:00Z",
  },
];

// ─── Forecast alerts (MAPE > 15%) ─────────────────────────────────────
export const MOCK_FORECAST_ALERTS: ForecastAlert[] = [
  {
    product_id: "SKU-008",
    product_name: "Sunscreen SPF50",
    category: "skincare",
    model_name: "xgboost_v1",
    mape: 0.2789,
    mape_pct: 27.89,
    mae: 198.6,
    hyperparameters: { n_estimators: 100, max_depth: 6, learning_rate: 0.1 },
    notes: "HIGH ERROR: summer seasonality not modeled",
    run_date: "2024-03-31",
  },
  {
    product_id: "SKU-004",
    product_name: "Keratin Hair Mask",
    category: "haircare",
    model_name: "xgboost_v1",
    mape: 0.2341,
    mape_pct: 23.41,
    mae: 124.6,
    hyperparameters: { n_estimators: 100, max_depth: 6, learning_rate: 0.1 },
    notes: "HIGH ERROR: underforecasting Q3 demand",
    run_date: "2024-03-31",
  },
  {
    product_id: "SKU-005",
    product_name: "Matte Lipstick",
    category: "cosmetics",
    model_name: "xgboost_v1",
    mape: 0.1876,
    mape_pct: 18.76,
    mae: 112.8,
    hyperparameters: { n_estimators: 100, max_depth: 6, learning_rate: 0.1 },
    notes: "HIGH ERROR: holiday spike not captured",
    run_date: "2024-03-31",
  },
];

// ─── AI Proposals (pending human approval) ────────────────────────────
export const MOCK_PROPOSALS: Proposal[] = [
  {
    id: "prop-001",
    type: "replenishment",
    status: "pending",
    severity: "CRITICAL",
    created_at: "2026-05-18T08:12:00Z",
    trigger: {
      product_id: "SKU-004",
      product_name: "Keratin Hair Mask",
      location: "West",
      metric: "stock_level",
      current_value: 95,
      threshold: 150,
    },
    agent_reasoning:
      "Keratin Hair Mask (West) is 37% below reorder point with a 8-day lead time from best supplier. At current depletion rate, stockout occurs in ~4 days. Recommending immediate PO to Bangalore Bio Products.",
    replenishment: {
      purchase_orders: [
        {
          po_number: "PO-A1B2C3D4",
          product_id: "SKU-004",
          product_name: "Keratin Hair Mask",
          location: "West",
          order_quantity: 505,
          unit_price: 19.99,
          order_value: 10094.95,
          supplier_name: "Bangalore Bio Products",
          lead_time_days: 8,
          expected_delivery: "2026-05-26",
        },
      ],
      total_order_value: 10094.95,
      supplier_name: "Bangalore Bio Products",
      lead_time_days: 8,
      expected_delivery: "2026-05-26",
    },
    trace_id: "trace-langgraph-001",
    latency_ms: 1240,
    nodes_visited: ["supervisor", "allocation_replenishment", "hitl"],
  },
  {
    id: "prop-002",
    type: "allocation",
    status: "pending",
    severity: "CRITICAL",
    created_at: "2026-05-18T08:14:00Z",
    trigger: {
      product_id: "SKU-001",
      product_name: "Moisturizing Face Cream",
      location: "Southeast",
      metric: "stock_level",
      current_value: 80,
      threshold: 100,
    },
    agent_reasoning:
      "Face Cream at Southeast has surplus at Northeast (450 units, buffer +350). Internal transfer of 20 units resolves the Southeast deficit immediately at zero procurement cost. Transfer recommended before PO.",
    allocation: {
      transfers: [
        {
          product_id: "SKU-001",
          product_name: "Moisturizing Face Cream",
          from_location: "Northeast",
          to_location: "Southeast",
          transfer_quantity: 20,
          reason: "Stock at Southeast is 20 units below reorder point",
        },
      ],
      total_units: 20,
    },
    trace_id: "trace-langgraph-002",
    latency_ms: 980,
    nodes_visited: ["supervisor", "allocation_replenishment", "hitl"],
  },
  {
    id: "prop-003",
    type: "forecast_tuning",
    status: "pending",
    severity: "HIGH",
    created_at: "2026-05-18T07:45:00Z",
    trigger: {
      product_id: "SKU-008",
      product_name: "Sunscreen SPF50",
      metric: "mape",
      current_value: 27.89,
      threshold: 15.0,
    },
    agent_reasoning:
      "Sunscreen SPF50 MAPE of 27.89% is driven by unmmodeled summer demand seasonality (Jun-Aug demand 2x baseline). Increasing n_estimators improves model capacity; adding month feature captures seasonal signal. Expected 8-12% MAPE reduction.",
    forecast_tuning: {
      old_params: { n_estimators: 100, max_depth: 6, learning_rate: 0.1 },
      new_params: { n_estimators: 200, max_depth: 8, learning_rate: 0.05 },
      rationale:
        "Double estimators for higher model capacity. Reduce learning rate for stability with more trees. Increase max_depth to capture summer-winter interaction patterns.",
      expected_mape_improvement: "~10% reduction (27.89% → ~18%)",
    },
    trace_id: "trace-langgraph-003",
    latency_ms: 2100,
    nodes_visited: ["supervisor", "forecasting", "hitl"],
  },
  {
    id: "prop-004",
    type: "replenishment",
    status: "approved",
    severity: "CRITICAL",
    created_at: "2026-05-18T06:30:00Z",
    trigger: {
      product_id: "SKU-006",
      product_name: "Foundation SPF30",
      location: "Southeast",
      metric: "stock_level",
      current_value: 180,
      threshold: 200,
    },
    agent_reasoning:
      "Foundation SPF30 at Southeast requires replenishment. PO approved and submitted to supplier.",
    replenishment: {
      purchase_orders: [
        {
          po_number: "PO-E5F6G7H8",
          product_id: "SKU-006",
          product_name: "Foundation SPF30",
          location: "Southeast",
          order_quantity: 720,
          unit_price: 29.99,
          order_value: 21592.8,
          supplier_name: "Mumbai Beauty Works",
          lead_time_days: 12,
          expected_delivery: "2026-05-30",
        },
      ],
      total_order_value: 21592.8,
      supplier_name: "Mumbai Beauty Works",
      lead_time_days: 12,
      expected_delivery: "2026-05-30",
    },
    trace_id: "trace-langgraph-004",
    latency_ms: 1180,
    nodes_visited: ["supervisor", "allocation_replenishment", "hitl"],
  },
];

// ─── Pipeline trace steps for a proposal ─────────────────────────────
export const MOCK_TRACE_STEPS: TraceStep[] = [
  {
    node: "supervisor",
    started_at: "2026-05-18T08:12:00.000Z",
    duration_ms: 320,
    status: "success",
    output_summary: 'Intent classified: "replenishment" — stock below reorder point detected',
  },
  {
    node: "allocation_replenishment",
    started_at: "2026-05-18T08:12:00.320Z",
    duration_ms: 2180,
    status: "success",
    tool_calls: [
      { tool: "inventory_lookup", latency_ms: 145, result_count: 4 },
      { tool: "POST /tasks (replenishment agent)", latency_ms: 2010 },
    ],
    output_summary: "Replenishment task delegated via A2A. 1 PO generated: $10,094.95",
  },
  {
    node: "hitl",
    started_at: "2026-05-18T08:12:02.500Z",
    duration_ms: 0,
    status: "success",
    output_summary: "Graph paused — awaiting human approval (interrupt() fired)",
  },
];

// ─── Dashboard summary stats ───────────────────────────────────────────
export const MOCK_STATS: DashboardStats = {
  critical_alerts: 4,
  pending_approvals: 3,
  approved_today: 1,
  total_po_value_pending: 10094.95,
  avg_mape: 14.8,
  services: [
    { name: "MCP Server", status: "healthy", latency_ms: 142 },
    { name: "Allocation Agent", status: "healthy", latency_ms: 38 },
    { name: "Replenishment Agent", status: "healthy", latency_ms: 41 },
    { name: "Postgres + pgvector", status: "healthy", latency_ms: 6 },
  ],
};
