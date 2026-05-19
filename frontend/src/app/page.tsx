"use client";

import { useState, useEffect, useCallback } from "react";
import { Navbar } from "@/components/Navbar";
import { StatsBar } from "@/components/StatsBar";
import { InventoryAlertsFeed } from "@/components/InventoryAlertsFeed";
import { ProposalCard } from "@/components/ProposalCard";
import { ForecastPanel } from "@/components/ForecastPanel";
import { api } from "@/lib/api";
import type { Proposal, DashboardStats, InventoryAlert, ForecastAlert } from "@/types";
import { RefreshCw } from "lucide-react";

// ─────────────────────────────────────────────
// Day 2: All mock data replaced with real API calls.
//
// Data flow:
//   browser → /api/dashboard/... (Next.js proxy route)
//           → http://localhost:8003/api/dashboard/... (FastAPI)
//           → PostgreSQL
//
// Why useCallback on loadData?
// We use it as a dependency in useEffect (the 30s poll interval).
// Without useCallback, a new function reference is created every render,
// causing the effect to re-run on every render — infinite loop.
// ─────────────────────────────────────────────

const EMPTY_STATS: DashboardStats = {
  critical_alerts: 0,
  pending_approvals: 0,
  approved_today: 0,
  po_value_pending: 0,
  avg_mape: 0,
  services: [
    { name: "MCP Server", status: "down" },
    { name: "Allocation Agent", status: "down" },
    { name: "Replenishment Agent", status: "down" },
  ],
};

export default function DashboardPage() {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [inventoryAlerts, setInventoryAlerts] = useState<InventoryAlert[]>([]);
  const [forecastAlerts, setForecastAlerts] = useState<ForecastAlert[]>([]);
  const [stats, setStats] = useState<DashboardStats>(EMPTY_STATS);

  const [activeFilter, setActiveFilter] = useState<"all" | "pending" | "approved" | "rejected">("all");
  const [lastRefresh, setLastRefresh] = useState(new Date());
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ── Load all dashboard data in parallel ──────────────────────────────────
  const loadData = useCallback(async () => {
    try {
      const [proposalsData, inventoryData, forecastData, statsData] =
        await Promise.all([
          api.getProposals(),
          api.getInventoryAlerts(),
          api.getForecastAlerts(),
          api.getStats(),
        ]);

      setProposals(proposalsData);
      setInventoryAlerts(inventoryData);
      setForecastAlerts(forecastData);
      setStats(statsData);
      setError(null);
    } catch (err) {
      console.error("Dashboard load error:", err);
      setError("Could not reach the Dashboard API. Is docker compose running?");
    } finally {
      setLoading(false);
      setLastRefresh(new Date());
    }
  }, []);

  // Initial load
  useEffect(() => {
    loadData();
  }, [loadData]);

  // Auto-refresh every 30s — Day 3 replaces this with SSE push
  useEffect(() => {
    const interval = setInterval(loadData, 30_000);
    return () => clearInterval(interval);
  }, [loadData]);

  // ── Approve handler ───────────────────────────────────────────────────────
  // Optimistically update UI, then confirm with API.
  // Day 4: this will also resume the LangGraph checkpoint via thread_id.
  const handleApprove = async (id: string) => {
    // Optimistic update
    setProposals((prev) =>
      prev.map((p) => (p.id === id ? { ...p, status: "approved" } : p))
    );
    setStats((prev) => ({
      ...prev,
      pending_approvals: Math.max(0, prev.pending_approvals - 1),
      approved_today: prev.approved_today + 1,
    }));

    try {
      await api.approveProposal(id);
    } catch (err) {
      // Rollback optimistic update on failure
      console.error("Approve failed:", err);
      setProposals((prev) =>
        prev.map((p) => (p.id === id ? { ...p, status: "pending" } : p))
      );
      setStats((prev) => ({
        ...prev,
        pending_approvals: prev.pending_approvals + 1,
        approved_today: Math.max(0, prev.approved_today - 1),
      }));
    }
  };

  // ── Reject handler ────────────────────────────────────────────────────────
  const handleReject = async (id: string) => {
    setProposals((prev) =>
      prev.map((p) => (p.id === id ? { ...p, status: "rejected" } : p))
    );
    setStats((prev) => ({
      ...prev,
      pending_approvals: Math.max(0, prev.pending_approvals - 1),
    }));

    try {
      await api.rejectProposal(id);
    } catch (err) {
      console.error("Reject failed:", err);
      setProposals((prev) =>
        prev.map((p) => (p.id === id ? { ...p, status: "pending" } : p))
      );
      setStats((prev) => ({
        ...prev,
        pending_approvals: prev.pending_approvals + 1,
      }));
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  };

  const filteredProposals = proposals.filter((p) =>
    activeFilter === "all" ? true : p.status === activeFilter
  );

  const pendingCount = proposals.filter((p) => p.status === "pending").length;

  // ── Error banner ──────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col">
        <Navbar stats={EMPTY_STATS} />
        <div className="flex-1 flex items-center justify-center">
          <div className="card p-8 max-w-md text-center space-y-3">
            <p className="text-red-400 font-semibold text-sm">Connection Error</p>
            <p className="text-slate-400 text-sm">{error}</p>
            <pre className="text-xs text-slate-600 text-left bg-slate-900 p-3 rounded-lg">
              docker compose up -d
            </pre>
            <button
              onClick={handleRefresh}
              className="btn-approve mx-auto"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Loading skeleton ──────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col">
        <Navbar stats={EMPTY_STATS} />
        <div className="flex-1 flex items-center justify-center">
          <div className="flex items-center gap-3 text-slate-400 text-sm">
            <RefreshCw className="w-4 h-4 animate-spin" />
            Connecting to Dashboard API...
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      <Navbar stats={stats} />

      <main className="flex-1 p-4 md:p-6 max-w-[1600px] mx-auto w-full space-y-4">

        {/* Stats bar */}
        <StatsBar stats={stats} />

        {/* Main 3-column grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 min-h-[600px]">

          {/* LEFT: Inventory alerts (3 cols) */}
          <div className="lg:col-span-3 h-[600px]">
            <InventoryAlertsFeed alerts={inventoryAlerts} />
          </div>

          {/* CENTER: Approval queue (6 cols) */}
          <div className="lg:col-span-6 flex flex-col gap-3">
            {/* Queue header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <h2 className="text-sm font-semibold text-white">Approval Queue</h2>
                {pendingCount > 0 && (
                  <span className="badge-critical">{pendingCount} pending</span>
                )}
              </div>

              <div className="flex items-center gap-2">
                {/* Filter tabs */}
                <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-0.5 text-xs">
                  {(["all", "pending", "approved", "rejected"] as const).map((f) => (
                    <button
                      key={f}
                      onClick={() => setActiveFilter(f)}
                      className={`px-2.5 py-1 rounded-md capitalize transition-colors ${
                        activeFilter === f
                          ? "bg-slate-700 text-white font-medium"
                          : "text-slate-500 hover:text-slate-300"
                      }`}
                    >
                      {f}
                    </button>
                  ))}
                </div>

                {/* Refresh */}
                <button
                  onClick={handleRefresh}
                  className="p-1.5 rounded-lg hover:bg-slate-800 border border-slate-800 transition-colors"
                  title="Refresh proposals"
                >
                  <RefreshCw
                    className={`w-3.5 h-3.5 text-slate-400 ${refreshing ? "animate-spin" : ""}`}
                  />
                </button>
              </div>
            </div>

            {/* Last refresh indicator */}
            <p className="text-[11px] text-slate-600 -mt-1">
              Last checked: {lastRefresh.toLocaleTimeString()} · Auto-refreshes every 30s
            </p>

            {/* Proposal cards */}
            <div className="space-y-3 overflow-y-auto max-h-[540px] pr-0.5">
              {filteredProposals.length === 0 ? (
                <div className="card p-8 text-center">
                  <p className="text-slate-500 text-sm">No proposals in this filter.</p>
                </div>
              ) : (
                filteredProposals.map((proposal) => (
                  <ProposalCard
                    key={proposal.id}
                    proposal={proposal}
                    onApprove={handleApprove}
                    onReject={handleReject}
                  />
                ))
              )}
            </div>
          </div>

          {/* RIGHT: Forecast health (3 cols) */}
          <div className="lg:col-span-3 h-[600px]">
            <ForecastPanel alerts={forecastAlerts} />
          </div>
        </div>

      </main>
    </div>
  );
}
