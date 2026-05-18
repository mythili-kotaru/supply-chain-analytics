"use client";

import { useState, useEffect } from "react";
import { Navbar } from "@/components/Navbar";
import { StatsBar } from "@/components/StatsBar";
import { InventoryAlertsFeed } from "@/components/InventoryAlertsFeed";
import { ProposalCard } from "@/components/ProposalCard";
import { ForecastPanel } from "@/components/ForecastPanel";
import {
  MOCK_INVENTORY_ALERTS,
  MOCK_FORECAST_ALERTS,
  MOCK_PROPOSALS,
  MOCK_STATS,
} from "@/lib/mock-data";
import type { Proposal, DashboardStats } from "@/types";
import { RefreshCw } from "lucide-react";

// ─────────────────────────────────────────────
// WHY useState for proposals?
// On Day 2 we'll replace this with a real API call + SSE subscription.
// For Day 1, local state lets us demo approve/reject interactions
// without any backend dependency.
// ─────────────────────────────────────────────

export default function DashboardPage() {
  const [proposals, setProposals] = useState<Proposal[]>(MOCK_PROPOSALS);
  const [stats, setStats] = useState<DashboardStats>(MOCK_STATS);
  const [activeFilter, setActiveFilter] = useState<"all" | "pending" | "approved" | "rejected">("all");
  const [lastRefresh, setLastRefresh] = useState(new Date());
  const [refreshing, setRefreshing] = useState(false);

  // Simulate a live "tick" — on Day 3 this becomes APScheduler events
  useEffect(() => {
    const interval = setInterval(() => {
      setLastRefresh(new Date());
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  // ─── Approve handler ──────────────────────────────────────────────────
  // Day 4: replace with POST /api/dashboard/proposals/{id}/approve
  // which resumes the LangGraph checkpoint
  const handleApprove = (id: string) => {
    setProposals((prev) =>
      prev.map((p) => (p.id === id ? { ...p, status: "approved" } : p))
    );
    setStats((prev) => ({
      ...prev,
      pending_approvals: Math.max(0, prev.pending_approvals - 1),
      approved_today: prev.approved_today + 1,
    }));
  };

  // ─── Reject handler ───────────────────────────────────────────────────
  const handleReject = (id: string) => {
    setProposals((prev) =>
      prev.map((p) => (p.id === id ? { ...p, status: "rejected" } : p))
    );
    setStats((prev) => ({
      ...prev,
      pending_approvals: Math.max(0, prev.pending_approvals - 1),
    }));
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    // Day 2: await fetch("/api/dashboard/proposals") here
    await new Promise((r) => setTimeout(r, 800));
    setLastRefresh(new Date());
    setRefreshing(false);
  };

  const filteredProposals = proposals.filter((p) =>
    activeFilter === "all" ? true : p.status === activeFilter
  );

  const pendingCount = proposals.filter((p) => p.status === "pending").length;

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
            <InventoryAlertsFeed alerts={MOCK_INVENTORY_ALERTS} />
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
              Last checked: {lastRefresh.toLocaleTimeString()} · Auto-monitored every 60s
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
            <ForecastPanel alerts={MOCK_FORECAST_ALERTS} />
          </div>
        </div>


      </main>
    </div>
  );
}
