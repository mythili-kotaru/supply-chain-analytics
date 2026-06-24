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
  SupplierModel,
  SupplierScorecardItem,
  SimulationParams,
  SimulationResponse,
} from "@/types";

// In Next.js, /api/... routes are always relative to the current origin
const BASE = "/api/dashboard";

const getRole = () => {
  if (typeof window !== "undefined") {
    return localStorage.getItem("scai_user_role") || "analyst";
  }
  return "analyst";
};

const getToken = () => {
  if (typeof window !== "undefined") {
    return localStorage.getItem("scai_access_token") || "";
  }
  return "";
};

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  headers.set("Content-Type", "application/json");
  headers.set("x-role", getRole());

  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }

  return res.json();
}

// ── Read endpoints ────────────────────────────────────────────────────────────

export const api = {
  login: (username: string, password: string) =>
    apiFetch<{ access_token: string; token_type: string; username: string; role: string; full_name: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password })
    }),

  getInventoryAlerts: () =>
    apiFetch<InventoryAlert[]>("/inventory/alerts"),

  getInventoryAll: () =>
    apiFetch<InventoryAlert[]>("/inventory/all"),

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

  getSuppliers: () =>
    apiFetch<SupplierModel[]>("/suppliers"),

  proposeSupplierConfig: (payload: { supplier_id: string; lead_time_days: number; defect_rate: number; rationale: string }) =>
    apiFetch<Proposal>("/proposals/supplier-config", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

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

  triggerMonitorRun: () =>
    apiFetch<{ status: string; results: Record<string, string> }>("/monitor/run", { method: "POST" }),

  runAnalyticsQuery: (query: string) =>
    apiFetch<any>("/analytics/query", {
      method: "POST",
      body: JSON.stringify({ query }),
    }),

  publishForecastReport: () =>
    apiFetch<{ status: string; page_id: string; title: string; url: string }>("/forecast/confluence-report", {
      method: "POST",
    }),

  // ── Sourcing & Supplier Scorecard ───────────────────────────────────────────

  getSourcingScorecard: () =>
    apiFetch<SupplierScorecardItem[]>("/sourcing/scorecard"),

  getSupplierScorecard: (supplierId: string) =>
    apiFetch<SupplierScorecardItem>(`/sourcing/scorecard/${supplierId}`),

  // ── Simulation / Scenario Sandbox (Day 11) ─────────────────────────────────

  runSimulation: (params: SimulationParams) =>
    apiFetch<SimulationResponse>("/simulation/run", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  // ── Charts ──────────────────────────────────────────────────────────────────

  getInventoryHealthChart: () =>
    apiFetch<Record<string, number>>("/charts/inventory-health"),

  getInventoryByCategoryChart: () =>
    apiFetch<{ category: string; avg_capacity_pct: number; sku_count: number; at_risk: number }[]>("/charts/inventory-by-category"),

  streamProposalApprove: async (
    id: string,
    onEvent: (event: any) => void
  ): Promise<any> => {
    const role = getRole();
    const token = getToken();
    const headers = new Headers();
    headers.set("Content-Type", "application/json");
    headers.set("x-role", role);
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    const response = await fetch(`${BASE}/proposals/${id}/approve/stream`, {
      method: "POST",
      headers,
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Stream error ${response.status}: ${body}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error("No readable stream in response");

    const decoder = new TextDecoder();
    let buffer = "";
    let finalResult = null;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data: ")) {
            const dataStr = trimmed.slice(6);
            try {
              const event = JSON.parse(dataStr);
              onEvent(event);
              if (event.event === "complete") {
                finalResult = event;
              }
            } catch (e) {
              console.error("Failed to parse stream event", dataStr, e);
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    return finalResult;
  },

  streamProposalReject: async (
    id: string,
    onEvent: (event: any) => void
  ): Promise<any> => {
    const role = getRole();
    const token = getToken();
    const headers = new Headers();
    headers.set("Content-Type", "application/json");
    headers.set("x-role", role);
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    const response = await fetch(`${BASE}/proposals/${id}/reject/stream`, {
      method: "POST",
      headers,
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Stream error ${response.status}: ${body}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error("No readable stream in response");

    const decoder = new TextDecoder();
    let buffer = "";
    let finalResult = null;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data: ")) {
            const dataStr = trimmed.slice(6);
            try {
              const event = JSON.parse(dataStr);
              onEvent(event);
              if (event.event === "complete") {
                finalResult = event;
              }
            } catch (e) {
              console.error("Failed to parse stream event", dataStr, e);
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    return finalResult;
  },

  streamChat: async (
    query: string,
    threadId: string | null,
    onEvent: (event: any) => void
  ): Promise<any> => {
    const role = getRole();
    const token = getToken();
    const headers = new Headers();
    headers.set("Content-Type", "application/json");
    headers.set("x-role", role);
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    const response = await fetch(`${BASE}/chat/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify({ query, thread_id: threadId }),
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Chat stream error ${response.status}: ${body}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error("No readable stream in response");

    const decoder = new TextDecoder();
    let buffer = "";
    let finalResult = null;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data: ")) {
            const dataStr = trimmed.slice(6);
            try {
              const event = JSON.parse(dataStr);
              onEvent(event);
              if (event.event === "complete") {
                finalResult = event;
              }
            } catch (e) {
              console.error("Failed to parse stream event", dataStr, e);
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }

    return finalResult;
  },
};
