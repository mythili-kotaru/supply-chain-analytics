/**
 * API client for the Dashboard API.
 *
 * WHY proxy through Next.js API routes instead of hitting FastAPI directly?
 * 1. No CORS config headaches — browser calls /api/... on the same origin
 * 2. We can add auth headers, rate limiting, or caching in one place
 * 3. The FastAPI URL is never exposed to the client (security)
 *
 * The Next.js API routes simply forward to:
 *   DASHBOARD_API_URL (default: http://localhost:8003)
 */

import type {
  InventoryAlert,
  ForecastAlert,
  Proposal,
  DashboardStats,
  DriftRecord,
  DriftHistory,
  AnomalyEvent,
} from "@/types";

// In Next.js, /api/... routes are always relative to the current origin
const BASE = "/api/dashboard";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }

  return res.json();
}

// ── Read endpoints ────────────────────────────────────────────────────────────

export const api = {
  getInventoryAlerts: () =>
    apiFetch<InventoryAlert[]>("/inventory/alerts"),

  getForecastAlerts: () =>
    apiFetch<ForecastAlert[]>("/forecast/alerts"),

  getProposals: (status?: "pending" | "approved" | "rejected") =>
    apiFetch<Proposal[]>(`/proposals${status ? `?status=${status}` : ""}`),

  getStats: () =>
    apiFetch<DashboardStats>("/stats"),

  // ── Write endpoints ─────────────────────────────────────────────────────────

  approveProposal: (id: string) =>
    apiFetch<{ id: string; status: string; message: string }>(
      `/proposals/${id}/approve`,
      { method: "POST" }
    ),

  rejectProposal: (id: string) =>
    apiFetch<{ id: string; status: string; message: string }>(
      `/proposals/${id}/reject`,
      { method: "POST" }
    ),

  // ── Drift detection ─────────────────────────────────────────────────────────

  getDriftSummary: () =>
    apiFetch<DriftRecord[]>("/forecast/drift"),

  getDriftHistory: (productId: string) =>
    apiFetch<DriftHistory>(`/forecast/drift/${productId}`),

  // ── Anomaly detection (Day 9) ───────────────────────────────────────────────

  getAnomalyEvents: (unackedOnly = false) =>
    apiFetch<AnomalyEvent[]>(`/anomaly/events${unackedOnly ? "?unacked_only=true" : ""}`),

  acknowledgeAnomaly: (id: number) =>
    apiFetch<{ id: number; acknowledged: boolean }>(`/anomaly/events/${id}/ack`, { method: "POST" }),

  triggerAnomalyScan: () =>
    apiFetch<{ status: string; summary: Record<string, unknown> }>("/anomaly/scan", { method: "POST" }),
};
