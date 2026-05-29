// types/index.ts
// These mirror the exact Postgres schema from 01_schema.sql
// When the backend API returns data, it will match these shapes exactly.

export type AlertSeverity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
export type ProposalStatus = "pending" | "approved" | "rejected" | "executing" | "done";
export type ProposalType = "replenishment" | "allocation" | "forecast_tuning";

// ─── Inventory alert (from inventory table) ───────────────────────────
export interface InventoryAlert {
  product_id: string;           // e.g. "SKU-008"
  product_name: string;         // e.g. "Sunscreen SPF50"
  category: string;             // "skincare" | "haircare" | "cosmetics"
  location: string;             // "Northeast" | "Southeast" | "West" | "Midwest"
  stock_level: number;          // current units
  reorder_point: number;        // trigger threshold
  max_capacity: number;
  capacity_pct: number;         // stock_level / max_capacity * 100
  status: "CRITICAL" | "LOW" | "OK";
  last_updated: string;
}

// ─── Forecast alert (from forecast_metrics table) ─────────────────────
export interface ForecastAlert {
  product_id: string;
  product_name: string;
  model_name: string;
  mape_pct: number;             // e.g. 27.89 (already multiplied by 100)
  hyperparameters: Record<string, string | number>;
  notes: string;
  run_date: string;
}

// ─── AI Proposal (the HITL approval unit) ─────────────────────────────
export interface Proposal {
  id: string;                   // UUID
  type: ProposalType;
  status: ProposalStatus;
  severity: AlertSeverity;
  created_at: string;

  // What triggered this proposal
  trigger: {
    product_id: string;
    product_name: string;
    location?: string;
    metric: string;             // "stock_level" | "mape"
    current_value: number;
    threshold: number;
  };

  // What the agent wants to do
  agent_reasoning: string;      // plain English explanation

  // Type-specific payload
  replenishment?: {
    purchase_orders: PurchaseOrder[];
    total_order_value: number;
    supplier_name: string;
    lead_time_days: number;
    expected_delivery: string;
  };

  allocation?: {
    transfers: AllocationTransfer[];
    total_units: number;
  };

  forecast_tuning?: {
    old_params: Record<string, number>;
    new_params: Record<string, number>;
    rationale: string;
    expected_mape_improvement: string;
  };

  // Trace info
  trace_id?: string;       // LangSmith run UUID
  trace_url?: string;      // Direct link to LangSmith run
  latency_ms?: number;
  nodes_visited?: string[];

  // Day 4: LangGraph thread_id — stored once /invoke pauses the graph.
  // Present when the langgraph_agent service is running.
  // Used by the approve/reject flow to resume the checkpointed graph.
  thread_id?: string;
}

export interface PurchaseOrder {
  po_number: string;
  product_id: string;
  product_name: string;
  location: string;
  order_quantity: number;
  unit_price: number;
  order_value: number;
  supplier_name: string;
  lead_time_days: number;
  expected_delivery: string;
}

export interface AllocationTransfer {
  product_id: string;
  product_name: string;
  from_location: string;
  to_location: string;
  transfer_quantity: number;
  reason: string;
}

// ─── Pipeline trace step ───────────────────────────────────────────────
export interface TraceStep {
  node: string;                 // "supervisor" | "sql_insights" | etc.
  started_at: string;
  duration_ms: number;
  status: "success" | "error";
  tool_calls?: {
    tool: string;
    latency_ms: number;
    result_count?: number;
  }[];
  output_summary: string;
}

// ─── Anomaly detection (Day 9) ─────────────────────────────────────────

export type AnomalyType = "stock_drop" | "demand_spike" | "mape_regression";

export interface AnomalyEvent {
  id: number;
  detected_at: string;
  anomaly_type: AnomalyType;
  severity: AlertSeverity;
  product_id: string;
  product_name: string;
  location: string | null;
  metric_name: string;
  metric_value: number;
  baseline_value: number;
  deviation_pct: number;
  anomaly_score: number;       // 0–1
  description: string;
  proposal_id: string | null;
  acknowledged: boolean;
  acknowledged_at: string | null;
}

// ─── Drift detection ───────────────────────────────────────────────────

export interface DriftRecord {
  id: string;
  product_id: string;
  product_name: string;
  status: string;
  old_params: Record<string, number>;
  new_params: Record<string, number>;
  rationale: string;
  pre_mape_pct: number | null;
  post_mape_pct: number | null;
  mape_delta_pct: number | null;
  improved: boolean | null;
  simulated: boolean;
  evaluated_at: string | null;
  proposed_at: string | null;
}

export interface DriftHistory {
  product_id: string;
  history: {
    run_date: string;
    mape_pct: number;
    notes: string;
    hyperparameters: Record<string, number>;
  }[];
}

// ─── Dashboard summary stats ───────────────────────────────────────────
export interface DashboardStats {
  critical_alerts: number;
  pending_approvals: number;
  approved_today: number;
  po_value_pending: number;
  avg_mape: number;
  services: {
    name: string;
    status: "healthy" | "degraded" | "down";
  }[];
}
