"""
Pydantic models for the Dashboard API.
These mirror the TypeScript interfaces in frontend/src/types/index.ts.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel


# ── Inventory ─────────────────────────────────────────────────────────────────

class InventoryAlert(BaseModel):
    product_id: str
    product_name: str
    category: str
    location: str
    stock_level: int
    reorder_point: int
    max_capacity: int
    capacity_pct: float      # stock_level / max_capacity * 100
    status: str              # CRITICAL | LOW | OK
    last_updated: str        # ISO string


# ── Forecast ──────────────────────────────────────────────────────────────────

class ForecastAlert(BaseModel):
    product_id: str
    product_name: str
    model_name: str
    mape_pct: float
    run_date: str
    notes: str
    hyperparameters: dict[str, Any]


# ── Proposals ─────────────────────────────────────────────────────────────────

class ProposalTrigger(BaseModel):
    product_id: str
    product_name: str
    location: Optional[str] = None
    metric: str              # 'stock_level' | 'mape_pct'
    current_value: float
    threshold: float


class PurchaseOrder(BaseModel):
    po_number: str
    supplier_id: str
    supplier_name: str
    order_quantity: int
    order_value: float
    lead_time_days: int
    expected_delivery: str


class ReplenishmentPayload(BaseModel):
    purchase_orders: list[PurchaseOrder]
    total_order_value: float


class AllocationTransfer(BaseModel):
    from_location: str
    to_location: str
    transfer_quantity: int
    reason: str


class AllocationPayload(BaseModel):
    transfers: list[AllocationTransfer]


class ForecastTuningPayload(BaseModel):
    model_name: str
    old_params: dict[str, Any]
    new_params: dict[str, Any]
    expected_mape_improvement: str


class Proposal(BaseModel):
    id: str
    type: str                # 'replenishment' | 'allocation' | 'forecast_tuning'
    status: str              # 'pending' | 'approved' | 'rejected'
    severity: str            # 'CRITICAL' | 'HIGH' | 'MEDIUM'
    created_at: str          # ISO string
    trigger: ProposalTrigger
    agent_reasoning: str
    latency_ms: Optional[int] = None
    nodes_visited: Optional[list[str]] = None
    thread_id: Optional[str] = None
    trace_id: Optional[str] = None      # LangSmith run UUID
    trace_url: Optional[str] = None     # LangSmith run URL for "View Trace →"
    replenishment: Optional[ReplenishmentPayload] = None
    allocation: Optional[AllocationPayload] = None
    forecast_tuning: Optional[ForecastTuningPayload] = None


# ── Stats ─────────────────────────────────────────────────────────────────────

class ServiceHealth(BaseModel):
    name: str
    status: str   # 'healthy' | 'degraded' | 'down'


class DashboardStats(BaseModel):
    critical_alerts: int
    pending_approvals: int
    approved_today: int
    po_value_pending: float
    avg_mape: float
    services: list[ServiceHealth]


# ── API responses ─────────────────────────────────────────────────────────────

class ApproveRejectResponse(BaseModel):
    id: str
    status: str
    message: str
