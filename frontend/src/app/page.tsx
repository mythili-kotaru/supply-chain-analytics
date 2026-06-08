"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { Navbar } from "@/components/Navbar";
import { StatsBar } from "@/components/StatsBar";
import { InventoryAlertsFeed } from "@/components/InventoryAlertsFeed";
import { ProposalCard } from "@/components/ProposalCard";
import { ForecastPanel } from "@/components/ForecastPanel";
import { DriftPanel } from "@/components/DriftPanel";
import { AnomalyFeed } from "@/components/AnomalyFeed";
import { useToast } from "@/components/Toast";
import { InventoryDonutChart } from "@/components/InventoryDonutChart";
import { CategoryCapacityBarChart } from "@/components/CategoryCapacityBarChart";
import { api } from "@/lib/api";
import type { Proposal, DashboardStats, InventoryAlert, ForecastAlert } from "@/types";
import { RefreshCw, Search } from "lucide-react";

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
    { name: "LangGraph Agent", status: "down" },   // Day 4
  ],
};

export default function DashboardPage() {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [inventoryAlerts, setInventoryAlerts] = useState<InventoryAlert[]>([]);
  const [forecastAlerts, setForecastAlerts] = useState<ForecastAlert[]>([]);
  const [stats, setStats] = useState<DashboardStats>(EMPTY_STATS);

  const [activeFilter, setActiveFilter] = useState<"all" | "pending" | "approved" | "rejected">("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [lastRefresh, setLastRefresh] = useState(new Date());
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { addToast } = useToast();

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
  // Day 4: No longer does an optimistic update — the ProposalCard manages
  // its own "Resuming agent…" spinner for the duration of the LangGraph run
  // (which can take 5-30s if A2A agents are doing real work).
  //
  // WHY drop optimistic update for Day 4?
  // The approve call now blocks until the LangGraph graph finishes execution.
  // Optimistic updates work great for fast calls (<200ms). For a 10s call,
  // the spinner in the card is better UX — it shows *real* progress status.
  //
  // After the graph completes, we refresh the proposal list to get the
  // updated status from the DB (which the langgraph_agent updated).
  const handleApprove = async (id: string) => {
    try {
      const result = await api.approveProposal(id);
      addToast("Proposal approved and executed successfully", "success");
      // Refresh proposals after LangGraph execution completes
      const updated = await api.getProposals();
      setProposals(updated);
      setStats((prev) => ({
        ...prev,
        pending_approvals: Math.max(0, prev.pending_approvals - 1),
        approved_today: prev.approved_today + 1,
      }));
      return result;
    } catch (err) {
      console.error("Approve failed:", err);
      addToast("Failed to approve proposal", "error");
      throw err;
    }
  };

  // ── Reject handler ────────────────────────────────────────────────────────
  const handleReject = async (id: string) => {
    try {
      const result = await api.rejectProposal(id);
      addToast("Proposal rejected", "info");
      const updated = await api.getProposals();
      setProposals(updated);
      setStats((prev) => ({
        ...prev,
        pending_approvals: Math.max(0, prev.pending_approvals - 1),
      }));
      return result;
    } catch (err) {
      console.error("Reject failed:", err);
      addToast("Failed to reject proposal", "error");
      throw err;
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  };

  const filteredProposals = useMemo(() => {
    return proposals.filter((p) => {
      const matchesFilter = activeFilter === "all" ? true : p.status === activeFilter;
      const q = searchQuery.toLowerCase();
      const matchesSearch = q === "" || 
        p.product_name?.toLowerCase().includes(q) || 
        p.action_type.toLowerCase().includes(q) ||
        p.location?.toLowerCase().includes(q);
      return matchesFilter && matchesSearch;
    });
  }, [proposals, activeFilter, searchQuery]);

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
        <main className="flex-1 p-4 md:p-6 max-w-[1600px] mx-auto w-full space-y-4">
          <div className="flex flex-col lg:flex-row gap-4">
            <div className="skeleton h-24 w-full" />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 min-h-[600px]">
            <div className="lg:col-span-3 skeleton h-[600px]" />
            <div className="lg:col-span-6 flex flex-col gap-3">
              <div className="skeleton h-10 w-full" />
              <div className="skeleton h-40 w-full" />
              <div className="skeleton h-40 w-full" />
              <div className="skeleton h-40 w-full" />
            </div>
            <div className="lg:col-span-3 skeleton h-[600px]" />
          </div>
        </main>
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
                {/* Search */}
                <div className="relative">
                  <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    placeholder="Search proposals..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="bg-slate-900 border border-slate-800 text-slate-200 text-xs rounded-lg pl-8 pr-3 py-1.5 focus:outline-none focus:border-slate-600 transition-colors w-40"
                  />
                </div>

                {/* Filter tabs */}
                <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-0.5 text-xs hidden sm:flex">
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

        {/* Anomaly Detection — live feed of scanner detections */}
        <AnomalyFeed />

        {/* Drift Detection — hyperparameter tuning outcomes */}
        <DriftPanel />

        {/* Analytics at a Glance — Chart.js visualisations */}
        <div className="space-y-3">
          <h2 className="text-base font-semibold text-white flex items-center gap-2">
            <span className="w-1.5 h-4 rounded-full bg-gradient-to-b from-violet-500 to-fuchsia-500" />
            Analytics at a Glance
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <InventoryDonutChart />
            <CategoryCapacityBarChart />
          </div>
        </div>

      </main>
    </div>
  );
}
